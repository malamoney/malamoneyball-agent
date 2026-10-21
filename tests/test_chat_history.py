def test_chat_history_survives_a_restart(run_chat):
    run_chat("Who should I start at QB?")
    history_seen = run_chat("What about at WR?")

    assert history_seen == [["Who should I start at QB?"]]


def test_exiting_the_chat_closes_the_history_database(run_chat, data_dir):
    run_chat("Who should I start at QB?")

    # SQLite removes its write-ahead files once the last connection closes.
    assert sorted(path.name for path in data_dir.iterdir()) == ["conversations.db"]
