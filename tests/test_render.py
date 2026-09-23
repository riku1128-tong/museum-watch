import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from render import closed_by_rule, judge, parse_price  # noqa: E402

MON = {"mon"}
M = {"id": "X", "status": "active"}


def detail(**kw):
    d = {
        "id": "X", "checked_at": "2026-09-24T06:00:00+09:00", "operating_status": "operating",
        "source_urls": [], "confidence": "high",
        "regular_hours": [{"days": ["tue", "wed", "thu", "sun"], "open": "09:30", "close": "17:30", "last_entry": "17:00"},
                          {"days": ["fri", "sat"], "open": "09:30", "close": "20:00"}],
        "closed_weekdays": ["mon"], "holiday_rule": "open_next_weekday_closed",
        "special_closures": [], "special_openings": [], "exhibitions": [],
    }
    d.update(kw)
    return d


def test_holiday_monday_open_and_next_weekday_closed():
    # 2026-10-12 はスポーツの日（月）
    assert closed_by_rule(date(2026, 10, 12), MON, "open_next_weekday_closed") == (False, None)
    closed, why = closed_by_rule(date(2026, 10, 13), MON, "open_next_weekday_closed")
    assert closed and "振替" in why
    assert closed_by_rule(date(2026, 10, 14), MON, "open_next_weekday_closed") == (False, None)


def test_consecutive_holidays_push_closure_to_first_weekday():
    # 2026-09-21(月・敬老の日) 22(火・国民の休日) 23(水・秋分の日) → 24(木) が振替休館
    for d in (21, 22, 23):
        assert closed_by_rule(date(2026, 9, d), MON, "open_next_weekday_closed")[0] is False
    assert closed_by_rule(date(2026, 9, 24), MON, "open_next_weekday_closed")[0] is True
    assert closed_by_rule(date(2026, 9, 25), MON, "open_next_weekday_closed")[0] is False


def test_rule_open_has_no_substitute_closure():
    assert closed_by_rule(date(2026, 10, 13), MON, "open")[0] is False
    assert closed_by_rule(date(2026, 10, 19), MON, "open") == (True, "定休日")


def test_holiday_closed_rule():
    assert closed_by_rule(date(2026, 11, 3), set(), "closed") == (True, "祝日休館")


def test_judge_hours_by_weekday_and_special_closure():
    r = judge(M, detail(), date(2026, 10, 9), date(2026, 9, 24))  # 金
    assert (r["status"], r["open"], r["close"]) == ("open", "09:30", "20:00")
    r = judge(M, detail(), date(2026, 10, 8), date(2026, 9, 24))  # 木
    assert (r["close"], r["last_entry"]) == ("17:30", "17:00")
    d = detail(special_closures=[{"from": "2026-12-28", "to": "2027-01-01", "reason": "年末年始"}])
    r = judge(M, d, date(2026, 12, 29), date(2026, 9, 24))
    assert (r["status"], r["reason"]) == ("closed", "年末年始")


def test_exhibition_hours_extend_museum_close_and_changeover_closure():
    ex = [{"title": "A展", "start": "2026-09-01", "end": "2026-10-10", "kind": "special",
           "hours": [{"days": ["thu"], "open": "09:30", "close": "21:00"}]},
          {"title": "B展", "start": "2026-10-20", "end": "2026-12-01", "kind": "special"}]
    d = detail(exhibitions=ex, closed_between_exhibitions=True)
    r = judge(M, d, date(2026, 10, 8), date(2026, 9, 24))  # 木
    assert r["close"] == "21:00" and r["exhibitions"][0]["title"] == "A展"
    r = judge(M, d, date(2026, 10, 15), date(2026, 9, 24))  # 展示替え
    assert (r["status"], r["reason"]) == ("closed", "展示替え期間")
    assert r["upcoming"][0]["title"] == "B展"


def test_stale_and_missing_details_need_check():
    assert judge(M, None, date(2026, 9, 24), date(2026, 9, 24))["status"] == "pending"
    r = judge(M, detail(checked_at="2026-09-16T06:00:00+09:00"), date(2026, 9, 25), date(2026, 9, 24))
    assert r["needs_check"] is True


def test_weekly_check_is_not_stale_within_the_week():
    r = judge(M, detail(checked_at="2026-09-18T06:00:00+09:00"), date(2026, 9, 25), date(2026, 9, 24))
    assert r["needs_check"] is False


def test_nth_weekday_closure_with_holiday_shift():
    nth = [{"weekday": "mon", "nth": [1, 3]}]
    rule = "open_next_weekday_closed"
    assert closed_by_rule(date(2026, 10, 5), set(), rule, nth)[0] is True    # 第1月曜
    assert closed_by_rule(date(2026, 10, 12), set(), rule, nth)[0] is False  # 第2月曜（祝日）
    assert closed_by_rule(date(2026, 10, 13), set(), rule, nth)[0] is False  # 第2月曜の振替は無い
    assert closed_by_rule(date(2026, 10, 19), set(), rule, nth)[0] is True   # 第3月曜
    # 9/21 は第3月曜かつ祝日 → 22,23 も祝日 → 9/24(木) が振替休館
    assert closed_by_rule(date(2026, 9, 21), set(), rule, nth)[0] is False
    assert closed_by_rule(date(2026, 9, 24), set(), rule, nth)[0] is True


def test_year_end_without_closure_info_needs_check():
    r = judge(M, detail(), date(2026, 12, 29), date(2026, 12, 27))
    assert r["status"] == "open" and r["needs_check"] is True
    d = detail(checked_at="2026-12-27T06:00:00+09:00", special_closures=[{"from": "2026-12-28", "to": "2027-01-01"}])
    assert judge(M, d, date(2027, 1, 2), date(2026, 12, 27))["needs_check"] is False


def test_narrower_period_hours_take_precedence():
    hours = [{"days": ["sat"], "open": "10:00", "close": "18:00"},
             {"days": ["sat"], "open": "10:00", "close": "20:00", "from": "2026-11-21", "to": "2026-11-22"}]
    r = judge(M, detail(regular_hours=hours, closed_weekdays=[]), date(2026, 11, 21), date(2026, 11, 20))
    assert r["close"] == "20:00"
    r = judge(M, detail(regular_hours=hours, closed_weekdays=[]), date(2026, 11, 28), date(2026, 11, 27))
    assert r["close"] == "18:00"


def test_weekday_override_beats_all_days_entry():
    hours = [{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "open": "09:30", "close": "17:00"},
             {"days": ["fri", "sat"], "open": "09:30", "close": "20:00"}]
    d = detail(regular_hours=hours, closed_weekdays=[])
    assert judge(M, d, date(2026, 10, 9), date(2026, 10, 8))["close"] == "20:00"   # 金
    assert judge(M, d, date(2026, 10, 8), date(2026, 10, 8))["close"] == "17:00"   # 木


def test_parse_price():
    assert parse_price("一般 2,300円") == 2300
    assert parse_price("大人 4,200円（変動価格制）") == 4200
    assert parse_price("大人・大学生 1,000円（日時指定予約制）") == 1000
    assert parse_price("無料") == 0
    assert parse_price("未定") is None


def test_free_days_and_rules():
    d = detail(free_days=[{"from": "2026-10-01", "to": "2026-10-01", "scope": "all", "reason": "都民の日"}],
               free_rules=[{"weekday": "sun", "nth": [1], "scope": "collection", "reason": "ファミリーデー"}])
    assert judge(M, d, date(2026, 10, 1), date(2026, 9, 30))["free"] == {"scope": "all", "reason": "都民の日"}
    assert judge(M, d, date(2026, 10, 4), date(2026, 9, 30))["free"]["scope"] == "collection"  # 第1日曜
    assert judge(M, d, date(2026, 10, 11), date(2026, 9, 30))["free"] is None
