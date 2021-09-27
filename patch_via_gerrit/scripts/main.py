#!/usr/bin/env python3

"""
Basic program to apply a set of patches from various Gerrit reviews
based on user criteria to a repo sync area (for purposes of testing)

The current logic is to apply the patches in order of the Gerrit review
IDs (e.g. 94172) once all relevant reviews have been determined
"""

import argparse
import configparser
import contextlib
import logging
import json
import os
import os.path
import re
import subprocess
import sys
import xml.etree.ElementTree as EleTree

import requests.exceptions

from pygerrit2 import GerritRestAPI, HTTPBasicAuth
from patch_via_gerrit.scripts._version import __version__, __build__


# Set up logging and handler
logger = logging.getLogger('patch_via_gerrit')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(levelname)s: %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)
handler.setLevel(logging.INFO)
logger.addHandler(handler)

class InvalidUpstreamException(Exception):
    def __init__(self, project):
        self.project = project
        self.message = f'Project {project} has an invalid upstream in manifest - is it locked to a sha?'
        super().__init__(self.message)

@contextlib.contextmanager
def cd(path):
    """Simple context manager to handle temporary directory change"""

    cwd = os.getcwd()

    try:
        os.chdir(path)
    except OSError:
        raise RuntimeError(f'Can not change directory to {path}')

    try:
        yield
    finally:
        os.chdir(cwd)


class ParseCSVs(argparse.Action):
    """Parse comma separated lists"""

    def __call__(self, parser, namespace, arguments, option_string=None):
        """
        Ensure all values separated by commas are parsed out; note that
        while quoted strings with spaces are preserved, a comma within
        quoted strings does NOT preserve
        """

        results = list()

        for arg in arguments:
            for value in arg.split(','):
                if len(value) > 0:
                    results.append(value)

        setattr(namespace, self.dest, results)


class GerritChange:
    """Encapsulation of relevant information for a given Gerrit review"""

    def __init__(self, data, patch_command):
        """
        Initialize with key information for a Gerrit review, including
        information about related parents
        """
        self._number = str(data['_number'])
        self.status = data['status']
        self.project = data['project']
        self.branch = data['branch']
        self.change_id = data['change_id']
        self.topic = data.get('topic')
        self.curr_revision = data['current_revision']
        revisions_info = data['revisions'][self.curr_revision]
        self.parents = [
            p['commit'] for p in revisions_info['commit']['parents']
        ]
        fetch_info = revisions_info['fetch']

        if 'anonymous http' in fetch_info:
            self.patch_command = \
                fetch_info['anonymous http']['commands'][patch_command]
        else:  # only other option is SSH
            self.patch_command = fetch_info['ssh']['commands'][patch_command]

        self.patch_command = re.sub('ssh://.*@', 'ssh://', self.patch_command)

class GerritPatches:
    """
    Determine all relevant patches to apply to a repo sync based on
    a given set of initial parameters, which can be a set of one of
    the following:
        - review IDs
        - change IDs
        - topics

    The resulting data will include the necessary patch commands to
    be applied to the repo sync
    """

    def __init__(self, gerrit_url, user, passwd, checkout=False):
        """Initial Gerrit connection and set base options"""

        auth = HTTPBasicAuth(user, passwd)
        self.rest = GerritRestAPI(url=gerrit_url, auth=auth)
        self.base_options = [
            'CURRENT_REVISION', 'CURRENT_COMMIT', 'DOWNLOAD_COMMANDS'
        ]
        self.patch_command = 'Checkout' if checkout else 'Cherry Pick'
        # We need to track reviews which were specifically requested as these
        # are applied regardless of their status. Derived reviews are only
        # applied if they are still open
        self.requested_reviews = []
        # We track what's been applied to ensure at least the changes we
        # specifically requested got done
        self.applied_reviews = []

    def query(self, query_string, options=None, quiet=False):
        """
        Get results from Gerrit for a given query string, returning
        a dictionary keyed off the relevant review IDs, the values
        being a special object containing all relevant information
        about a review
        """

        if options is None:
            options = self.base_options

        opt_string = '&o='.join([''] + options)
        data = dict()

        try:
            q_string = query_string + opt_string
            logger.debug(f"  Query is: {q_string}")
            results = self.rest.get(q_string)
        except requests.exceptions.HTTPError as exc:
            raise RuntimeError(exc)
        else:
            for result in results:
                num_id = str(result['_number'])
                data[num_id] = GerritChange(result, self.patch_command)
        if not quiet:
            logger.debug(f'  Review IDs from query: {", ".join(list(data))}')

        return data

    def get_changes_via_review_id(self, review_id):
        """Find all reviews for a given review ID"""

        # Query review ID directly first to ensure it exist and is readable
        # This filters out invalid and inaccessible "prviate" review IDs.
        # A "private" review ID is a review marked "private" by the owner so that no one else can see it.
        # Only gerrit admin and users with "View Private Changes" permission can see a "private" review.
        logger.debug(f'Ensuring review ID {review_id} is not private')
        if ( len(self.query(f'/changes/?q={review_id}', quiet=True)) == 0 ):
            logger.error(
                f'Query returns no data for {review_id}!\n'
                'It is either invalid or marked as "private" by its owner.\n'
                'A "private" review is only accessible by users with "View Private Changes" permission.'
            )
            sys.exit(1)

        logger.debug(f'Querying on review ID {review_id}')
        status = "status:open+" if review_id not in self.requested_reviews else ""
        return self.query(f'/changes/?q={status}{review_id}')

    def get_changes_via_change_id(self, change_id):
        """Find all reviews for a given change ID"""

        logger.debug(f'Querying on change ID {change_id}')
        return self.query(f'/changes/?q=status:open+change:{change_id}')

    def get_changes_via_topic_id(self, topic):
        """Find all reviews for a given topic"""

        logger.debug(f'Querying on topic {topic}')
        return self.query(f'/changes/?q=status:open+topic:{topic}')

    def get_open_parents(self, review):
        """Find all open parent reviews for a given review"""

        reviews = dict()

        if not review or not review.parents:
            return reviews

        # Search recursively up via the parents until no more
        # open reviews are found
        for parent in review.parents:
            logger.debug(f'Querying on parent review sha: {parent}')
            p_review = self.query(f'/changes/?q=status:open+commit:{parent}')
            if not p_review:
                continue
            p_review_id = list(p_review.keys())[0]  # Always single element
            reviews.update(p_review)
            reviews.update(self.get_open_parents(p_review[p_review_id]))

        logger.debug('Found parents: {}'.format(
            ', '.join([str(r) for r in reviews]))
        )

        return reviews

    def get_reviews(self, initial_args, id_type):
        """
        From an initial set of parameters (review IDs, change IDs or
        topics), determine all relevant open reviews that will need
        to be applied to a repo sync via patching
        """
        all_reviews = dict()
        stack = list()

        # Generate initial set of reviews from the initial set
        # of parameters, generating the stack (list of review IDs)
        # from the results
        for initial_arg in initial_args:
            reviews = getattr(
                self, f'get_changes_via_{id_type}_id'
            )(initial_arg)
            review_ids = [r_id for r_id in reviews.keys()]
            logger.debug('Initial review IDs: {}'.format(
                ', '.join([str(r_id) for r_id in review_ids])
            ))

            stack.extend(review_ids)

        logger.info("Finding dependent reviews...")

        # From the stack, check each entry and add to the final set
        # of reviews if not already there and we have not already
        # applied a patch bearing the same change_id to a different
        # branch of the same project.
        #
        # We keep track of which change have been seen so far, and
        # look for any related reviews via change ID and topic, along
        # with any still open parents, adding to the stack as needed.
        #
        # All relevant reviews will have been found once the stack
        # is empty.
        while stack:
            review_id = stack.pop()
            reviews = self.get_changes_via_review_id(review_id)

            for new_id, review in reviews.items():
                if new_id in all_reviews.keys():
                    continue

                # Stop processing a review if one has already been added
                # for the same project and change_id (e.g. if the
                # incoming review is on a different branch to one we've
                # already applied)
                if [k for k, v in all_reviews.items()
                    if v.project == review.project
                        and v.change_id == review.change_id]:
                    break

                all_reviews[new_id] = review

                change_reviews = self.get_changes_via_change_id(
                    review.change_id
                )

                stack.extend(
                    [r_id for r_id in change_reviews.keys()
                     if r_id not in all_reviews.keys()]
                )

                if review.topic is not None:
                    topic_reviews = self.get_changes_via_topic_id(
                        review.topic
                    )
                    stack.extend(
                        [r_id for r_id in topic_reviews.keys()
                         if r_id not in all_reviews.keys()]
                    )

                # No need to get the parents When using git Checkout
                # Checkout will get the parents automatically
                if self.patch_command != "Checkout":
                    stack.extend(
                        [r_id for r_id in self.get_open_parents(review)
                         if r_id not in all_reviews.keys()]
                    )

        # When using checkout, remove parents from the reviews.
        # Checkout of a child will apply all its parents
        if self.patch_command == "Checkout":
            for r_id in sorted (all_reviews):
                for p_id in self.get_open_parents(all_reviews[r_id]):
                    if p_id in all_reviews:
                        del all_reviews[p_id]
                        logger.info(
                            f'Remove {p_id}.  Checkout of its child review {r_id} '
                            'already include the change.')

        logger.info('Final list of review IDs to apply: {}'.format(
            ', '.join([str(r_id) for r_id in all_reviews.keys()])
        ))

        return all_reviews

    def check_requested_reviews_applied(self):
        # If one or more of our requested reviews doesn't appear in applied reviews,
        # something the user asked for didn't happen. Error out with some info.
        if any(item not in self.applied_reviews for item in self.requested_reviews):
            logger.critical(
                "Failed to apply all explicitly-requested review IDs! "
                f'Requested: {self.requested_reviews} '
                f'Applied: {self.applied_reviews}'
            )
            sys.exit(1)
        else:
            logger.info(
                f"All explicitly-requested review IDs applied! {self.requested_reviews}"
            )

    def apply_single_review(self, review, proj_path):
        """
        Given a single review object from Gerrit and a path, apply
        the git change to that path (using either checkout or cherry-pick
        as requested).
        """

        if not os.path.exists(proj_path):
            # Project is missing on disk, but we expected to find it:
            # that's bad.
            logger.critical(
                f'***** Project {review.project} missing on disk! '
                f'Expected to be in {proj_path}'
            )
            sys.exit(5)

        try:
            logger.info(f'***** Applying review {review._number} to project {review.project}:')
            with cd(proj_path):
                subprocess.check_call(review.patch_command, shell=True)
                self.applied_reviews.append(review._number)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f'Patch for review {review.id} failed: {exc.output}'
            )
        logger.info(f'***** Done applying review {review._number} to project {review.project}')


    def patch_repo_sync(self, review_ids, id_type):
        """
        Patch the repo sync with the list of patch commands. Repo
        sync is presumed to be in current working directory.
        """

        # Compute full set of reviews
        reviews = self.get_reviews(review_ids, id_type)

        # Pull out any changes for the 'manifest' project and apply them
        # first, to the local repo manifest. If there are any such changes,
        # re-run repo sync afterwards.
        manifest_changes_found = False
        for review_id in sorted(reviews.keys()):
            review = reviews[review_id]
            if review.project == "manifest":
                manifest_changes_found = True
                del reviews[review_id]
                self.apply_single_review(
                    review,
                    os.path.join(".repo", "manifests")
                )

        # If there were manifest changes, re-run "repo sync"
        if manifest_changes_found:
            subprocess.check_call(['repo', 'sync', '--jobs=4'])

        # Read in the manifest. We ask repo to report the manifest, because
        # that automatically filters out projects that were not synced due
        # to groups ("repo init -g ....", or being in "notdefault" group).
        manixml = subprocess.check_output(['repo', 'manifest'])
        mf = EleTree.fromstring(manixml)

        # Iterate over all discovered reviews, applying the changes
        for review_id in sorted(reviews.keys()):
            review = reviews[review_id]
            proj_info = mf.find(
                f'.//project[@name="{review.project}"]'
            )
            if proj_info is None:
                logger.info(
                    f"***** NOTE: ignoring review ID {review_id} for project "
                    f"{review.project} that is either not part of the "
                    "manifest, or was excluded due to manifest group filters."
                )
                continue

            path = proj_info.attrib.get('path', review.project)
            self.apply_single_review(review, path)
        self.check_requested_reviews_applied()

def main():
    """
    Parse the arguments, verify the repo sync exists, read and validate
    the configuration file, then determine all the needed Gerrit patches
    and apply them to the repo sync
    """

    # PyInstaller binaries get LD_LIBRARY_PATH set for them, and that
    # can have unwanted side-effects for our subprocesses.
    os.environ.pop("LD_LIBRARY_PATH", None)

    version_string = f"patch_via_gerrit version {__version__} (build {__build__})"

    parser = argparse.ArgumentParser(
        description='Patch repo sync with requested Gerrit reviews'
    )
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Enable debugging output')
    parser.add_argument('-c', '--config', dest='gerrit_config',
                        help='Configuration file for patching via Gerrit',
                        default='patch_via_gerrit.ini')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-r', '--review-id', dest='review_ids', nargs='+',
                       action=ParseCSVs, help='review IDs to apply (comma-separated)')
    group.add_argument('-g', '--change-id', dest='change_ids', nargs='+',
                       action=ParseCSVs, help='change IDs to apply (comma-separated)')
    group.add_argument('-t', '--topic', dest='topics', nargs='+',
                       action=ParseCSVs, help='topics to apply (comma-separated)')
    parser.add_argument('-s', '--source', dest='repo_source', required=True,
                        help='Location of the repo sync checkout')
    parser.add_argument('-C', '--checkout', action='store_true',
                        help='When specified, patch_via_gerrit will checkout '
                        'relevant changes rather than cherry pick')
    parser.add_argument('-V', '--version', action='version',
                        help='Display patch_via_gerrit version information',
                        version=version_string)
    args = parser.parse_args()

    # Set logging to debug level on stream handler if --debug was set
    if args.debug:
        handler.setLevel(logging.DEBUG)

    if not os.path.isdir(args.repo_source):
        logger.error(
            "Path for repo sync checkout doesn't exist.  Aborting..."
        )
        sys.exit(1)
    os.chdir(args.repo_source)

    gerrit_config = configparser.ConfigParser()
    gerrit_config.read(args.gerrit_config)

    if 'main' not in gerrit_config.sections():
        logger.error(
            f'Invalid or unable to read config file "{args.gerrit_config}"'
        )
        sys.exit(1)

    try:
        gerrit_url = gerrit_config.get('main', 'gerrit_url')
        user = gerrit_config.get('main', 'username')
        passwd = gerrit_config.get('main', 'password')
    except configparser.NoOptionError:
        logger.error(
            'One of the options is missing from the config file: '
            'gerrit_url, username, password.  Aborting...'
        )
        sys.exit(1)

    # Initialize class to allow connection to Gerrit URL, determine
    # type of starting parameters and then find all related reviews
    gerrit_patches = GerritPatches(gerrit_url, user, passwd, args.checkout)

    if args.review_ids:
        id_type = 'review'
        review_ids = args.review_ids
        gerrit_patches.requested_reviews = args.review_ids
    elif args.change_ids:
        id_type = 'change'
        review_ids = args.change_ids
    else:
        id_type = 'topic'
        review_ids = args.topics

    logger.info(f"******** {version_string} ********")
    if review_ids is None:
        logger.info("No patches requested, so doing nothing")
        sys.exit(0)

    logger.info(f"Initial request to patch {id_type}s: {', '.join(review_ids)}")

    gerrit_patches.patch_repo_sync(review_ids, id_type)

if __name__ == '__main__':
    try:
        main()
    except InvalidUpstreamException as e:
        print(e)
        sys.exit(1)
