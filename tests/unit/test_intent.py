from mining_rights_agent.agent.intent import parse_intent


def test_parse_pilbara_chinese_request() -> None:
    intent = parse_intent("给我生成一份关于 Pilbara 锂矿近14天的简报")

    assert intent.project == "Pilbara"
    assert intent.company == "Pilbara Minerals"
    assert intent.commodity == "lithium"
    assert intent.days == 14


def test_parse_copper_request() -> None:
    intent = parse_intent("Create a 5 day copper brief for Example Mine")

    assert intent.commodity == "copper"
    assert intent.days == 5
