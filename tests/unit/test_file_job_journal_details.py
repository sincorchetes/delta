"""The mark that says a backup was under way, made where it has to be."""

from delta.infrastructure.file_job_journal import FileJobJournal


def test_the_folder_of_the_mark_is_made_with_the_folders_above_it(tmp_path):
    journal = FileJobJournal(tmp_path / "state" / "of" / "delta")

    journal.begin()

    assert journal.was_interrupted()
