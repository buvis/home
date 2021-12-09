import pyautogui
from datetime import datetime


dt_now = datetime.now()
minute = dt_now.minute
if minute % 4 == 0:
    pyautogui.press('numlock')
    pyautogui.press('numlock')
