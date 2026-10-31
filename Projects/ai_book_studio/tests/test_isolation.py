"""Two browsers must never see, open, delete or take over each other's books."""

from __future__ import annotations

import pytest

from components.identity import is_valid_owner
from utils.retry_utils import ProjectLoadError

ALICE = "alice-token-0123456789abcdef"
BOB = "bob-token-0123456789abcdefgh"


def test_each_owner_only_lists_their_own_books(storage, book_input):
    mine = storage.create_project(book_input, owner=ALICE)
    theirs = storage.create_project(book_input, owner=BOB)

    assert [p["id"] for p in storage.list_projects(owner=ALICE)] == [mine.project_id]
    assert [p["id"] for p in storage.list_projects(owner=BOB)] == [theirs.project_id]
    assert storage.latest_project_id(owner=ALICE) == mine.project_id
    assert {p["id"] for p in storage.list_projects()} == {mine.project_id, theirs.project_id}


def test_owner_survives_saving_and_reloading(storage, book_input):
    project = storage.create_project(book_input, owner=ALICE)
    storage.save_all(project)
    assert storage.load_project(project.project_id).owner == ALICE
    assert storage.owner_of(project.project_id) == ALICE


def test_cannot_open_someone_elses_book(storage, book_input):
    project = storage.create_project(book_input, owner=ALICE)
    with pytest.raises(ProjectLoadError):
        storage.load_project(project.project_id, owner=BOB)
    assert storage.load_project(project.project_id, owner=ALICE).project_id == project.project_id


def test_cannot_delete_someone_elses_book(storage, book_input):
    project = storage.create_project(book_input, owner=ALICE)
    with pytest.raises(ProjectLoadError):
        storage.delete_project(project.project_id, owner=BOB)
    assert storage.project_dir(project.project_id).exists()
    storage.delete_project(project.project_id, owner=ALICE)
    assert not storage.project_dir(project.project_id).exists()


def test_empty_owner_never_matches_anything(storage, book_input):
    legacy = storage.create_project(book_input)  # no owner, like a book from before owners existed
    assert storage.list_projects(owner="") == []
    with pytest.raises(ProjectLoadError):
        storage.load_project(legacy.project_id, owner="")


def test_unowned_books_are_hidden_until_adopted_once(storage, book_input):
    legacy = storage.create_project(book_input)
    owned = storage.create_project(book_input, owner=BOB)
    assert storage.list_projects(owner=ALICE) == []

    assert storage.adopt_unowned(ALICE) == 1
    assert [p["id"] for p in storage.list_projects(owner=ALICE)] == [legacy.project_id]
    assert storage.owner_of(owned.project_id) == BOB  # books that already have an owner are never taken
    assert storage.adopt_unowned(BOB) == 0


def test_owner_token_validation():
    assert is_valid_owner(ALICE)
    assert not is_valid_owner("")
    assert not is_valid_owner(None)
    assert not is_valid_owner("short")
    assert not is_valid_owner("x" * 20 + "';alert(1);//")
