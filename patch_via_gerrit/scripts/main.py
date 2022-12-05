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

default_whitelist = ["unstable"]

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


def default_ini_file():
    """
    Returns a string path to the default patch_via_gerrit.ini
    """
    return os.path.join(
        os.path.expanduser('~'), '.ssh', 'patch_via_gerrit.ini'
    )


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

    def __init__(self, gerrit_url, user, passwd, checkout=False, whitelist_branches=[]):
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
        # Manifest project name (could theoretically be dynamic)
        self.manifest = None
        # The manifest is only read from disk if manifest_stale is true. This
        # is to facilitate a re-read in the event a patch is applied to the
        # manifest itself
        self.manifest_stale = True
        self.manifest_project = 'manifest'
        self.ignore_manifest = False
        self.only_manifest = False
        # We use this regex to determine if the revision is a sha, for a
        # given project in the manifest
        self.sha_re = re.compile(r'[0-9a-f]{40}')
        self.whitelist_branches = whitelist_branches


    @classmethod
    def from_config_file(cls, config_path, checkout=False, whitelist_branches=[]):
        """
        Factory method: construct a GerritPatches from the path to a config file
        """
        if not os.path.exists(config_path):
            logger.error(f'Configuration file {config_path} missing!')
            sys.exit(1)

        gerrit_config = configparser.ConfigParser()
        gerrit_config.read(config_path)

        if 'main' not in gerrit_config.sections():
            logger.error(
                f'Invalid config file "{config_path}" (missing "main" section)'
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

        return cls(gerrit_url, user, passwd, checkout, whitelist_branches)


    def set_only_manifest(self, only_manifest):
        self.only_manifest = only_manifest


    def set_ignore_manifest(self, ignore_manifest):
        self.ignore_manifest = ignore_manifest


    def get_project_path_and_branch_from_manifest(self, project):
        branch = None
        path = None
        if self.manifest_stale:
            # Read in the manifest. We ask repo to report the manifest, because
            # that automatically filters out projects that were not synced due
            # to groups ("repo init -g ....", or being in "notdefault" group).
            manifest_str = subprocess.check_output(['repo', 'manifest'])
            self.manifest = EleTree.fromstring(manifest_str)
            self.manifest_stale = False

        proj_info = self.manifest.find(
                f'.//project[@name="{project}"]'
        )
        if proj_info != None:
            path = proj_info.attrib.get('path', project)
            branch = proj_info.attrib.get('revision')
            if branch == None:
                default = self.manifest.find(".//default")
                if default != None:
                    branch = default.attrib.get('revision')
        return (path, branch)


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
                # Always cherry-pick for manifest project
                if result['project'] == self.manifest_project:
                    patch_command = "Cherry Pick"
                else:
                    patch_command = self.patch_command
                data[num_id] = GerritChange(result, patch_command)
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
        if ( len(self.query(f'/changes/?q=change:{review_id}', quiet=True)) == 0 ):
            logger.error(
                f'Query returns no data for {review_id}!\n'
                'It is either invalid or marked as "private" by its owner.\n'
                'A "private" review is only accessible by users with "View Private Changes" permission.'
            )
            sys.exit(1)

        logger.debug(f'Querying on review ID {review_id}')
        status = "status:open+" if review_id not in self.requested_reviews else ""
        return self.query(f'/changes/?q={status}change:{review_id}')


    def get_changes_via_change_id(self, change_id):
        """Find all reviews for a given change ID"""

        logger.debug(f'Querying on change ID {change_id}')
        return self.query(f'/changes/?q=status:open+change:{change_id}')


    def get_changes_via_topic_id(self, topic):
        """Find all reviews for a given topic"""

        logger.debug(f'Querying on topic {topic}')
        return self.query(f'/changes/?q=status:open+topic:"{topic}"')


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
                for p_id in self.get_open_parents(all_reviews.get(r_id)):
                    if p_id in all_reviews:
                        del all_reviews[p_id]
                        logger.info(
                            f'Remove {p_id}.  Checkout of its child review {r_id} '
                            'already include the change.')

        for id, review in all_reviews.copy().items():
            (_, manifest_branch) = self.get_project_path_and_branch_from_manifest(review.project)
            if (manifest_branch
                and id not in self.requested_reviews
                and review.branch not in self.whitelist_branches
                and review.branch != manifest_branch
                and not self.sha_re.match(manifest_branch)):
                # Note: in this conditional we REJECT changes which match all
                # four of these criteria:
                # - review ID was not explicitly requested
                # - review branch does not appear in whitelist_branches
                # - review branch does not match manifest revision
                # - manifest revision does not point at a sha
                logger.info(f"  Ignoring {review._number} because it's for {review.branch}, manifest branch is {manifest_branch}")
                del all_reviews[id]

        logger.info('Final list of review IDs to apply: {}'.format(
            ', '.join([str(r_id) for r_id in all_reviews.keys()])
        ))

        return all_reviews


    def check_requested_reviews_applied(self):
        # If one or more of our requested reviews doesn't appear in applied reviews,
        # something the user asked for didn't happen. Error out with some info.
        if any(
            item not in self.applied_reviews
            for item in self.requested_reviews
        ):
            logger.critical(
                f"Failed to apply all explicitly-requested review IDs! "
                f'Requested: {self.requested_reviews} '
                f'Applied: {self.applied_reviews}'
            )
            sys.exit(1)
        elif self.requested_reviews:
            logger.info(
                f"All explicitly-requested review IDs applied! "
                f'Requested: {self.requested_reviews} '
                f'Applied: {self.applied_reviews}'
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

        logger.info(
            f'***** Applying https://review.couchbase.org/'
            f'{review._number} to project {review.project}:'
        )
        try:
            with cd(proj_path):
                subprocess.check_call(review.patch_command, shell=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f'Patch for review {review.id} failed: {exc.output}'
            )
        logger.info(
            f'***** Done applying review {review._number} '
            f'to project {review.project}\n'
        )
        self.applied_reviews.append(review._number)


    def apply_manifest_reviews(self, reviews):
        """
        Digs out and applies all changes to the 'manifest' project.
        Re-runs "repo sync" if any such changes found.
        """

        logger.info("Looking for reviews on the 'manifest' project...")
        manifest_changes_found = False
        for review_id in sorted(reviews.keys()):
            review = reviews[review_id]
            if review.project == self.manifest_project:
                del reviews[review_id]
                manifest_changes_found = True
                self.apply_single_review(
                    review,
                    os.path.join(".repo", "manifests")
                )

        # If there were manifest changes, re-run "repo sync"
        if manifest_changes_found:
            self.manifest_stale = True
            subprocess.check_call(['repo', 'sync', '--jobs=4'])


    def apply_non_manifest_reviews(self, reviews):
        """
        Applies all changes NOT to the 'manifest' project.
        """

        logger.info("Looking for reviews to non-manifest projects...")
        for review_id in sorted(reviews.keys()):
            review = reviews[review_id]
            if review.project == self.manifest_project:
                if self.ignore_manifest:
                    logger.debug(
                        f"Ignoring review {review_id} for 'manifest' project"
                    )
                    continue
                logger.fatal(
                    f"Found review {review_id} for 'manifest' project - "
                    "should not happen at this stage!"
                )
                sys.exit(5)

            (path, branch) = \
                self.get_project_path_and_branch_from_manifest(review.project)

            if (path, branch) == (None, None):
                logger.info(
                    f"***** NOTE: ignoring review ID {review_id} for project "
                    f"{review.project} that is either not part of the "
                    f"manifest, or was excluded due to manifest group filters."
                )
                continue

            self.apply_single_review(review, path)


    def patch_repo_sync(self, review_ids, id_type):
        """
        Patch the repo sync with the list of patch commands. Repo
        sync is presumed to be in current working directory.
        """

        # Compute full set of reviews
        reviews = self.get_reviews(review_ids, id_type)

        # Apply them all - manifest reviews first
        if not self.ignore_manifest:
            self.apply_manifest_reviews(reviews)
        if not self.only_manifest:
            self.apply_non_manifest_reviews(reviews)

        # Only do this check when doing a full apply
        if not self.only_manifest and not self.ignore_manifest:
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
    default_config_file = default_ini_file()
    parser = argparse.ArgumentParser(
        description='Patch repo sync with requested Gerrit reviews'
    )
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Enable debugging output')
    parser.add_argument('-c', '--config', dest='gerrit_config',
                        help='Configuration file for patching via Gerrit',
                        default=default_config_file)
    change_group = parser.add_mutually_exclusive_group(required=True)
    change_group.add_argument('-r', '--review-id', dest='review_ids', nargs='+',
                       action=ParseCSVs, help='review IDs to apply (comma-separated)')
    change_group.add_argument('-g', '--change-id', dest='change_ids', nargs='+',
                       action=ParseCSVs, help='change IDs to apply (comma-separated)')
    change_group.add_argument('-t', '--topic', dest='topics', nargs='+',
                       action=ParseCSVs, help='topics to apply (comma-separated)')
    parser.add_argument('-w', '--whitelist-branches', nargs='+',
                        dest='whitelist_branches',
                        action=ParseCSVs,
                        help='Branches to which changes can be applied even if '
                        'they don\'t match the revision in the manifest',
                        default=default_whitelist)
    manifest_group = parser.add_mutually_exclusive_group(required=False)
    manifest_group.add_argument('--ignore-manifest', action='store_true',
                                help='Do not apply any changes to "manifest" repo')
    manifest_group.add_argument('--only-manifest', action='store_true',
                                help='Apply only changes to "manifest" repo')
    parser.add_argument('-s', '--source', dest='repo_source',
                        help='Location of the repo sync checkout',
                        default='.')
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

    # Initialize class to allow connection to Gerrit URL, determine
    # type of starting parameters and then find all related reviews
    gerrit_patches = GerritPatches.from_config_file(
        args.gerrit_config,
        args.checkout,
        args.whitelist_branches
    )
    if args.only_manifest:
        gerrit_patches.set_only_manifest(True)
    elif args.ignore_manifest:
        gerrit_patches.set_ignore_manifest(True)

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
