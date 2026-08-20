from __future__ import annotations
from datetime import date
import calendar
import re

CATEGORY_RULES = [
    ("property_tax", ("grundsteuer","grundbesitz","gemeindeabgabe")),
    ("insurance", ("versicherung","wohngebäude","haftpflicht")),
    ("interest", ("darlehenszins","schuldzins","zinsen","kreditzins")),
    ("repairs", ("reparatur","instandhaltung","instandsetzung","handwerker","wartung","sanierung")),
    ("management", ("verwaltung","verwalter","hausverwaltung")),
    ("nonalloc_operating", ("bankgebühr","kontoführung","nicht umlagefähig")),
    ("reserve_contribution", ("erhaltungsrücklage","instandhaltungsrücklage","rücklage")),
]

def suggest_tax_category(title: str, notes: str = "") -> str:
    text=(title+" "+notes).lower()
    for category, words in CATEGORY_RULES:
        if any(w in text for w in words):
            return category
    return "other_expense"

def active_months_for_year(start_date: str|None, end_date: str|None, year: int) -> list[int]:
    start=date(year,1,1)
    end=date(year,12,31)
    try:
        if start_date:
            y,m,d=map(int,start_date[:10].split("-")); start=max(start,date(y,m,d))
        if end_date:
            y,m,d=map(int,end_date[:10].split("-")); end=min(end,date(y,m,d))
    except Exception:
        pass
    if start>end:
        return []
    months=[]
    for m in range(1,13):
        first=date(year,m,1)
        last=date(year,m,calendar.monthrange(year,m)[1])
        if first<=end and last>=start:
            months.append(m)
    return months

def annual_rent_schedule(monthly_cold_rent: float, start_date: str|None, end_date: str|None, year: int):
    months=active_months_for_year(start_date,end_date,year)
    value=round(float(monthly_cold_rent or 0),2)
    return [{"month":m,"amount":value} for m in months]
