import os
import pytest
import patch_via_gerrit.scripts.patch_via_gerrit as app
import patch_via_gerrit.tests.conftest as conftest

def test_check_env_vars():
    source_path = os.getenv('source_path')
    gerrit_url = os.getenv('gerrit_url')
    gerrit_user = os.getenv('gerrit_user')
    gerrit_pass = os.getenv('gerrit_pass')
    if None in [source_path, gerrit_url, gerrit_user, gerrit_pass]:
        pytest.exit("Missing environment variable/s")

def test_cd():
    with app.cd("/usr/bin"):
        assert os.getcwd() == "/usr/bin"

class TestGerritPatches:
    source_path = os.getenv('source_path')
    gerrit_patches = app.GerritPatches(os.getenv('gerrit_url'), os.getenv('gerrit_user'), os.getenv('gerrit_pass'), source_path)

    def reset(self):
        self.gerrit_patches.applied_reviews = []
        self.gerrit_patches.requested_reviews = []
        conftest.reset_checkout()

    def test_rest_get(self):
        # getting via rest API
        assert self.gerrit_patches.rest.get("/changes/?q=owner:self%20status:open")

    def test_fail_to_get_one_review(self):
        # landing on a sys.exit(1) if we request a review which can't be applied
        self.gerrit_patches.requested_reviews = ['111111']
        self.gerrit_patches.get_reviews(['111111'], 'review')
        with pytest.raises(SystemExit) as e:
            self.gerrit_patches.check_requested_reviews_applied()
        assert e.type == SystemExit
        assert e.value.code == 1

    def test_get_one_review(self):
        # getting one review
        reviews = list(self.gerrit_patches.get_reviews(['134808'], 'review'))
        assert reviews == ['134808']

    def test_get_one_closed_review(self):
        # getting one closed review
        reviews = list(self.gerrit_patches.get_reviews(['152371'], 'review'))
        assert reviews == []

    def test_get_two_reviews(self):
        # getting two reviews
        reviews = list(self.gerrit_patches.get_reviews(['134808', '134809'], 'review'))
        reviews.sort()
        assert reviews == ['134808', '134809']

    def test_get_changes_via_review_id(self):
        # getting a change via review id
        changes = self.gerrit_patches.get_changes_via_review_id(134808)
        assert changes['134808'].change_id == 'Ic2e7bfd58bd4fcf3be5330338f9376f1a958cf6a'

    def test_get_merged_changes_via_review_id(self):
        # getting a merged change via review id, we want this to return nothing
        # we only want to find closed changes if we've explicitly passed them
        # as an argument via -r
        changes = list(self.gerrit_patches.get_changes_via_review_id('152371'))
        assert changes == []

    def test_get_merged_changes_via_review_id_when_requested(self):
        # getting a change via review id when it has been specifically requested
        # note: main() adds these to gerrit_patches.requested_reviews to make
        # these easier to track + test
        self.gerrit_patches.requested_reviews = ['152371']
        changes = self.gerrit_patches.get_changes_via_review_id('152371')
        assert changes['152371'].change_id == 'I9b798eac330661e49e7da02491a1506e3298bb19'

    def test_get_changes_via_change_id(self):
        # getting a review via a change id
        changes = list(self.gerrit_patches.get_changes_via_change_id('Ic2e7bfd58bd4fcf3be5330338f9376f1a958cf6a'))
        assert changes == ['134808']

    def test_get_changes_via_topic_id(self):
        # getting changes via a topic id
        # note: we don't use topics in gerrit, this just tests getting an empty response
        changes = self.gerrit_patches.get_changes_via_topic_id('dummyvalue')
        assert not changes

    def test_get_open_parents(self):
        # todo: need to do this with a change which has parents too.
        change = self.gerrit_patches.get_open_parents(self.gerrit_patches.get_changes_via_review_id('134808')['134808'])
        assert not change

    def test_patch_repo_sync_master_branch(self):
        # applying a single patch on master
        self.reset()
        self.gerrit_patches.patch_repo_sync(['134808'], 'review')
        assert os.path.exists(f'{self.source_path}/tlm/test/change1')

    def test_patch_repo_sync_madhatter_branch(self):
        # applying a single patch on mad hatter (should be applied because although manifest points at master
        # for that project, we are passing this review explicitly)
        self.reset()
        self.gerrit_patches.patch_repo_sync(['134811'], 'review')
        assert os.path.exists(f'{self.source_path}/tlm/test/change3')

    def test_patch_repo_sync_master_branch_shared_change_id(self):
        # applying a single patch on the master branch, which shares its change_id with a similar change on mad-hatter
        self.reset()
        self.gerrit_patches.patch_repo_sync(['134812'], 'review')
        assert os.path.exists(f'{self.source_path}/tlm/test/change4a') \
            and not os.path.exists(f'{self.source_path}/tlm/test/change4b')

    def test_patch_repo_sync_mad_hatter_branch_shared_change_id(self):
        # applying a single patch on the mad-hatter branch, which shares its change_id with a similar change on master
        # only mad-hatter change should apply, as it was explicitly specified
        self.reset()
        self.gerrit_patches.patch_repo_sync(['134814'], 'review')
        assert not os.path.exists(f'{self.source_path}/tlm/test/change4a') \
            and os.path.exists(f'{self.source_path}/tlm/test/change4b')

    def test_patch_repo_sync_multiple_changes_with_shared_id_by_review_id(self):
        # applying multiple changes, one of which:
        #   applies an explicit change to mad-hatter although manifest references master
        #   shares its change_id with a change on master which should *not* be applied
        #   shares its change_id with a change in geocouch which *should* be applied
        self.reset()
        self.gerrit_patches.patch_repo_sync(['134808', '134814'], 'review')
        assert os.path.exists(f'{self.source_path}/tlm/test/change1') \
            and not os.path.exists(f'{self.source_path}/tlm/test/change4a') \
            and os.path.exists(f'{self.source_path}/tlm/test/change4b') \
            and os.path.exists(f'{self.source_path}/geocouch/test/change4c')

    def test_patch_repo_sync_multiple_changes_with_shared_id_by_review_id_2(self):
        # applying a single geocouch change which shares a change ID with:
        #   a tlm/master change (which should be applied)
        #   a tlm/mad-hatter change (which should be ignored)
        self.reset()
        self.gerrit_patches.patch_repo_sync(['134874'], 'review')
        assert  os.path.exists(f'{self.source_path}/tlm/test/change4a') \
            and not os.path.exists(f'{self.source_path}/tlm/test/change4b') \
            and os.path.exists(f'{self.source_path}/geocouch/test/change4c')
