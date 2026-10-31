from src import model_client


def test_think_blocks_are_removed_from_a_stream():
    chunks = ["<th", "ink>plan the ", "answer</thi", "nk>\n\nHello ", "there"]
    assert "".join(model_client.strip_think_blocks(iter(chunks))) == "Hello there"
    assert "".join(model_client.strip_think_blocks(iter(["Plain <b>text</b> a < b"]))) == "Plain <b>text</b> a < b"


def test_unfinished_think_block_is_never_spoken():
    assert "".join(model_client.strip_think_blocks(iter(["Hi 秘密"]))) == "Hi "