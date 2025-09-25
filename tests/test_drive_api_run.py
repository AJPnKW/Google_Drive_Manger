# test_drive_api_run.py
from src.google_drive_manager.drive_api import sync_folder, DriveAPIError

# Minimal fake service implementing files().list() used by find_file_by_name/list_files
class FakeFilesList:
    def __init__(self, result):
        self._result = result
    def list(self, q=None, pageSize=100, fields=None):
        # return an object with execute()
        class Exec:
            def __init__(self, data):
                self._data = data
            def execute(self):
                return self._data
        return Exec({"files": self._result})

class FakeFiles:
    def __init__(self, result):
        self._result = result
    def list(self, *args, **kwargs):
        return FakeFilesList(self._result).list()
    # other mutating methods are not called in dry_run path

class FakeService:
    def __init__(self, files_result=None):
        self._files_result = files_result or []
    def files(self):
        return FakeFiles(self._files_result)

def main():
    service_stub = FakeService(files_result=[])  # pretend Drive has no files with same name
    try:
        results = sync_folder(service_stub, local_dir="docs", drive_parent_id=None, dry_run=True)
        print("Dry-run sync results (first 20):")
        for r in results[:20]:
            print(r)
        print("Total actions planned:", len(results))
    except DriveAPIError as e:
        print("DriveAPIError:", e)
    except Exception as exc:
        print("Unexpected error:", exc)

if __name__ == "__main__":
    main()
