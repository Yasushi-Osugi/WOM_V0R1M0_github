#calendar445.py
import datetime
class Calendar445:
    def __init__(self, start_year: int, plan_range: int):
        self.start_year = start_year
        self.plan_range = plan_range
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
        for y in range(self.plan_range):
            year = self.start_year + y
            weeks_in_month = [4, 4, 5] * 4
            if year in self.use_53week_years:
                weeks_in_month[-1] += 1  # 53週対応
            for m_idx, w in enumerate(weeks_in_month):
                label = f"{year % 100:02}{m_idx + 1:02}"
                week_labels[week] = label
                week += w
        return week_labels
    def get_month_end_weeks(self):
        week = 1
        ends = []
        for y in range(self.plan_range):
            year = self.start_year + y
            weeks_in_month = [4, 4, 5] * 4
            if year in self.use_53week_years:
                weeks_in_month[-1] += 1
            for w in weeks_in_month:
                ends.append(week + w - 1)
                week += w
        return ends
