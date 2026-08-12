import pytest

from astock.sources.tencent import (
    normalize_code,
    parse_kline_payload,
    parse_quote_payload,
)

QUOTE_TEXT = (
    'v_sh600000="1~浦发银行~600000~9.17~9.21~9.21~467825~227739~240086~9.17~1364~9.16~3823~'
    "9.15~3573~9.14~1853~9.13~3583~9.18~251~9.19~2300~9.20~5343~9.21~4293~9.22~3554~~"
    "20260812161441~-0.04~-0.43~9.22~9.12~9.17/467825/429212224~467825~42921~0.14~5.96~~"
    "9.22~9.12~1.09~3054.15~3054.15~0.41~10.13~8.29~0.74~-1545~9.17~4.93~6.11~~~0.05~"
    '42921.2224~56.8558~620~   A~GP-A~-23.71~-0.97~4.58~6.03~0.49~13.83~8.07~-1.19~3.15~'
    '7.50~33305838300~33305838300~-5.16~-18.12~33305838300~~~-31.92~-0.11~~CNY~0~___D__F__N~9.11~6439~";\n'
)


def test_parse_quote_payload():
    (quote,) = parse_quote_payload(QUOTE_TEXT)
    assert quote.code == "sh600000"
    assert quote.name == "浦发银行"
    assert quote.price == 9.17
    assert quote.prev_close == 9.21
    assert quote.change == -0.04
    assert quote.change_pct == -0.43
    assert quote.high == 9.22
    assert quote.low == 9.12
    assert quote.volume == 46782500  # 手 → 股
    assert quote.amount == 429212224
    assert quote.pe_ttm == 5.96
    assert quote.pb == 0.41
    assert quote.total_mcap == 3054.15
    assert quote.kind == "GP-A"
    assert quote.time == "2026-08-12T16:14:41"


STAR_QUOTE_TEXT = (
    'v_sh688981="1~中芯国际~688981~127.96~125.41~126.00~43837992~23232838~20605154~127.95~691~'
    "127.94~48~127.93~9~127.92~16~127.91~421~127.96~578~127.97~506~127.98~68~127.99~156~"
    "128.00~884~~20260812161443~2.55~2.03~128.50~124.51~127.96/43837992/5553551712~43837992~"
    "555355~2.19~217.12~~128.50~124.51~3.18~2558.64~10954.73~5.75~150.49~100.33~0.85~-1007~"
    "126.68~201.19~217.32~~~2.14~555355.1712~411.2123~32136~A RA~GP-A-KCB~4.18~2.00~0.00~3.37~"
    "1.70~176.34~88.00~-2.25~-16.71~7.69~1999562549~8561059513~-29.82~8.28~1999562549~~~44.55~"
    '-0.03~~CNY~0~___D__F__NY~128.01~-118~100";\n'
)


def test_star_market_volume_is_reported_in_shares():
    (quote,) = parse_quote_payload(STAR_QUOTE_TEXT)
    assert quote.kind == "GP-A-KCB"
    assert quote.volume == 43837992  # already shares, must not be scaled by 100
    assert quote.amount == 5553551712
    assert quote.amount / quote.volume == pytest.approx(quote.price, rel=0.05)


def test_parse_quote_payload_skips_empty_entries():
    assert parse_quote_payload('v_sh600001="";\n') == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("600000", "sh600000"),
        ("sh600000", "sh600000"),
        ("600000.SS", "sh600000"),
        ("000001", "sz000001"),
        ("300750", "sz300750"),
        ("000001.SZ", "sz000001"),
        ("830799", "bj830799"),
        (" 688981 ", "sh688981"),
    ],
)
def test_normalize_code(raw, expected):
    assert normalize_code(raw) == expected


def test_normalize_code_rejects_garbage():
    with pytest.raises(ValueError):
        normalize_code("not-a-code")


def test_parse_kline_payload():
    payload = {
        "data": {
            "sh600000": {
                "qfqday": [
                    ["2026-08-11", "9.270", "9.210", "9.340", "9.180", "509424.000"],
                    ["2026-08-12", "9.210", "9.170", "9.220", "9.120", "467825.000"],
                ]
            }
        }
    }
    candles = parse_kline_payload(payload, "sh600000", "day")
    assert [c.date for c in candles] == ["2026-08-11", "2026-08-12"]
    assert candles[-1].close == 9.17
    assert candles[-1].volume == 467825.0
