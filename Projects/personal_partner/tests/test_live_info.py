from src import live_info


def test_state_name_is_found_in_common_questions():
    assert live_info._state_name("who is cm of tamilnadu") == "Tamil Nadu"


def test_cm_question_gets_targeted_hint_title():
    assert live_info._hint_title("who is cm of tamilnadu", 2026) == "Chief Minister of Tamil Nadu"


def test_film_question_gets_yearly_list_hint_title():
    title = live_info._hint_title("tell me some good latest tamil films", 2026)
    assert title == "List of Tamil films of 2026"


def test_table_titles_reads_first_link_of_each_row():
    raw = (
        "{| class=\"wikitable\"\n! Rank !! Title\n"
        "|-\n!1\n| ''[[Jana Nayagan]]''\n| [[Some Studio]]\n"
        "|-\n!2\n| ''[[Karuppu (film)|Karuppu]]''<ref>cite</ref>\n"
        "|}"
    )
    assert live_info._table_titles(raw) == ["Jana Nayagan", "Karuppu"]


def test_table_titles_skips_file_links_and_rows_without_links():
    raw = "|-\n| [[File:Poster.jpg]]\n|-\n| no link here\n|-\n| [[Leo]]\n"
    assert live_info._table_titles(raw) == ["Leo"]
