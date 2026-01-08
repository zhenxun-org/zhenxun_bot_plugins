from datetime import date, timedelta

import chinese_calendar as calendar
import lunardate

# 定义2026年农历节日的农历日期
lunar_festivals = {
    "春节": (1, 1),  # 春节 (农历正月初一)
    "端午节": (5, 5),  # 端午节 (农历五月初五)
    "中秋节": (8, 15),  # 中秋节 (农历八月十五)
}

# 固定日期的节日
fixed_festivals_dates = {
    "劳动节": date(2026, 5, 1),  # 劳动节
    "国庆节": date(2026, 10, 1),  # 国庆节
    "元旦": date(2026, 1, 1),  # 元旦
}


def get_next_year_festival_date(
    festival_name: str, current_festival_date: date
) -> date:
    """获取下一个该节日的日期"""
    if festival_name not in lunar_festivals:
        # 对于固定日期的节日，直接增加一年
        return current_festival_date.replace(year=current_festival_date.year + 1)

    # 对于农历节日，使用lunardate库转换为下一年的公历日期
    next_year = current_festival_date.year + 1
    month, day = lunar_festivals[festival_name]
    return lunardate.LunarDate(next_year, month, day).toSolarDate()


def find_tomb_sweeping_day(year: int) -> date:
    # 春分通常在3月20日或21日
    start_date = date(year, 3, 20)

    # 查找春分的确切日期
    spring_equinox = next(
        (
            start_date + timedelta(days=i)
            for i in range(3)
            if calendar.get_holiday_detail(start_date + timedelta(days=i))[1] == "春分"
        ),
        start_date,
    )
    return spring_equinox + timedelta(days=15)


def days_until_festival(festival_name: str, today: date, festival_date: date) -> int:
    if festival_date < today:
        # 如果节日已经过去，计算下一个该节日的到来时间
        next_festival_date = get_next_year_festival_date(festival_name, festival_date)
        delta = next_festival_date - today
    else:
        delta = festival_date - today

    return delta.days


# 获取农历节日对应的公历日期
def get_lunar_festivals_dates(today: date):
    year = today.year
    return {
        name: lunardate.LunarDate(year, month, day).toSolarDate()
        for name, (month, day) in lunar_festivals.items()
    }


def get_festivals_dates() -> list[tuple[int, str]]:
    today = date.today()
    lunar_festivals_dates = get_lunar_festivals_dates(today)
    # 添加清明节到节日字典中
    lunar_festivals_dates["清明节"] = find_tomb_sweeping_day(today.year)

    # 合并两个字典
    festivals_dates = {**lunar_festivals_dates, **fixed_festivals_dates}

    sort_name = ["春节", "端午节", "中秋节", "清明节", "劳动节", "国庆节", "元旦"]

    # 计算到每个节日的天数，并检查是否为法定假日
    data_list = []
    for name in sort_name:
        if name in festivals_dates:
            days_left = days_until_festival(name, today, festivals_dates[name])
            data_list.append((days_left, name))
        else:
            data_list.append((-1, name))
    data_list.sort(key=lambda x: x[0])
    return data_list
