import pytest

from typing import Mapping

from fv3net.pipelines.kube_jobs import wait_for_complete


class dotdict(dict):
    """dot.notation access to dictionary attributes"""

    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


class MockBatchV1ApiResponse(object):
    """
    Mock of the response dictionary object from BatchV1Api
    """

    def __init__(self, items):
        self.items = items

    @classmethod
    def from_args(cls, num_jobs: int, num_successful: int, labels: Mapping[str, str]):
        """
        Args:
            num_jobs: Number of fake jobs to create
            active_jobs: Number of jobs to mark as active. Should be > 1
            num_successful: Number of jobs to mark as successful.
            labels: Labels to apply to all generated jobs.
        """

        items = []
        for i in range(num_jobs):

            job_name = f"job{i}"
            success = int(i + 1 <= num_successful)
            info = cls._gen_job_info(job_name, success, labels)
            items.append(info)

        return cls(items)

    @staticmethod
    def _gen_job_info(
        job_name: str, success: bool, labels: Mapping[str, str],
    ):

        info = dotdict(
            metadata=dotdict(labels=labels, name=job_name, namespace="default",),
            status=dotdict(
                active=1,
                failed=(1 if not success else None),
                succeeded=(1 if success else None),
            ),
        )

        return info

    def delete_job_item(self, job_name, job_namespace):

        for i, job_item in enumerate(self.items):
            curr_job_name = job_item.metadata.name
            curr_job_namespace = job_item.metadata.namespace
            if job_name == curr_job_name and job_namespace == curr_job_namespace:
                break

        del self.items[i]

    def make_jobs_inactive(self):

        for job_item in self.items:
            job_item.status.active = None

    def get_job_and_namespace_tuples(self):

        results = []
        for job_info in self.items:
            metadata = job_info.metadata
            res_tuple = (metadata.name, metadata.namespace)
            results.append(res_tuple)

        return results

    def get_response_with_matching_labels(self, labels):

        items = []
        for job_info in self.items:
            job_labels = job_info.metadata.labels
            labels_match = self._check_labels_in_job_info(job_labels, labels)
            if labels_match:
                items.append(job_info)

        return self.__class__(items)

    @staticmethod
    def _check_labels_in_job_info(job_labels, check_labels):
        for label_key, label_value in check_labels.items():
            item = job_labels.get(label_key, None)
            if item is not None and item == label_value:
                return True

        return False


class MockBatchV1Api(object):

    """
    Mock of kubernetes.client.BatchV1Api to test kube_job.utils
    """

    def __init__(self, mock_response: MockBatchV1ApiResponse):

        self.response = mock_response
        self.num_list_calls = 0

    def list_job_for_all_namespaces(self, label_selector):

        # switch to non-active to kill the wait loop after 1 call
        if self.num_list_calls >= 1:
            self.response.make_jobs_inactive()
        elif self.num_list_calls > 5:
            raise TimeoutError("Probably stuck in a loop.")

        self.num_list_calls += 1

        label_dict = self._parse_label_selector(label_selector)
        return self.response.get_response_with_matching_labels(label_dict)

    @staticmethod
    def _parse_label_selector(label_selector):

        kv_pairs = [kv_pair.split("=") for kv_pair in label_selector.split(",")]
        labels_dict = {k: v for k, v in kv_pairs}

        return labels_dict

    def delete_namespaced_job(self, job_name, namespace):

        self.response.delete_job_item(job_name, namespace)


@pytest.fixture
def mock_batch_api():

    num_jobs = 4
    num_success = 3
    labels = {"test-group": "test-label", "group2": "grp2-label"}
    mock_response = MockBatchV1ApiResponse.from_args(num_jobs, num_success, labels)
    mock_api = MockBatchV1Api(mock_response)

    return num_jobs, num_success, mock_api, labels


def test_wait_for_complete(mock_batch_api):

    num_jobs, num_sucess, batch_client, labels = mock_batch_api
    success, fail = wait_for_complete(
        labels, batch_client=batch_client, sleep_interval=2
    )

    assert len(success) == num_sucess
    assert len(fail) == num_jobs - num_sucess