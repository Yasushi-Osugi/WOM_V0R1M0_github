#calendar445.py
# call example
#
#cal = Calendar445(
#    start_year=2026,
#    plan_range=5,
#    use_13_months=True,
#    holiday_country="JP"
#)
#
#week_labels = cal.get_week_labels()
#month_ends = cal.get_month_end_weeks()
#holiday_weeks = cal.get_holiday_weeks()
import datetime
class Calendar445:
    def __init__(self, start_year: int, plan_range: int, use_13_months=False, holiday_country=None):
        self.start_year = start_year
        self.plan_range = plan_range
        self.use_13_months = use_13_months
        self.holiday_country = holiday_country
        self.use_53week_years = self.get_53week_years()
    def get_53week_years(self):
        result = []
        for year in range(self.start_year, self.start_year + self.plan_range):
            if datetime.date(year, 12, 31).weekday() == 4:  # 金曜日 = 4
                result.append(year)
        return result
    def get_week_labels(self):
        week_labels = {}
        week = 1
        if self.use_13_months:
            months = [4] * 13
        else:
            months = [4, 4, 5] * 4
        for y in range(self.plan_range):
            year = self.start_year + y
            current_months = months.copy()
            if not self.use_13_months and year in self.use_53week_years:
                current_months[-1] += 1  # 53週対応（第12月に追加）
            elif self.use_13_months and year in self.use_53week_years:
                current_months[-1] += 1  # 13期制でも最終月に追加
            for m_idx, w in enumerate(current_months):
                label = f"{year % 100:02}{m_idx + 1:02}" if not self.use_13_months else f"{year % 100:02}{m_idx + 1}"
                week_labels[week] = label
                week += w
        return week_labels
    def get_month_end_weeks(self):
        week = 1
        ends = []
        if self.use_13_months:
            months = [4] * 13
        else:
            months = [4, 4, 5] * 4
        for y in range(self.plan_range):
            year = self.start_year + y
            current_months = months.copy()
            if not self.use_13_months and year in self.use_53week_years:
                current_months[-1] += 1
            elif self.use_13_months and year in self.use_53week_years:
                current_months[-1] += 1
            for w in current_months:
                ends.append(week + w - 1)
                week += w
        return ends
    def get_holiday_weeks(self):
        if not self.holiday_country:
            return []
        try:
            import holidays
        except ImportError:
            print("Please install the 'holidays' package to use holiday features.")
            return []
        holiday_weeks = set()
        for y in range(self.start_year, self.start_year + self.plan_range):
            hdays = holidays.country_holidays(self.holiday_country, years=[y])
            for date in hdays:
                week_num = date.isocalendar()[1]  # ISO週番号を取得
                year_offset = y - self.start_year
                week_index = year_offset * 53 + week_num
                holiday_weeks.add(week_index)
        return sorted(holiday_weeks)
