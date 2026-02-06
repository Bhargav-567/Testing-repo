# In your app/templatetags/exam_filters.py
from django import template

register = template.Library()

@register.filter
def char(value):
    """Convert ASCII number to character (65=A, 66=B, etc.)"""
    try:
        return chr(int(value))
    except (ValueError, TypeError):
        return ''
