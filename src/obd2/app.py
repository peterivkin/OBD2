VERSION = "1"

"""
Чтение OBDII
"""

import asyncio
import math
import threading
import time
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

from obd2.elm327 import *
from obd2.obd_client import OBDClient


import logging
from pathlib import Path

logger = setup_logging()
logger.info(f"Logger : {logger}")

JavaClass = None

try:
    # В BeeWare на Android используется Chaquopy, где доступен модуль 'java'
    from java import jclass
    JavaClass = jclass
    logger.info("Используется нативный Java bridge (Chaquopy)")
except ImportError:
    try:
        from rubicon.java import JavaClass
        logger.info("Используется Rubicon-Java")
    except Exception:
        JavaClass = None
        logger.error("Java bridge недоступен (это нормально для Windows/Linux)")





def haversine_m(lat1, lon1, lat2, lon2):
    """Расстояние между двумя GPS-точками в метрах (формула гаверсинуса)."""
    R = 6371000.0  # радиус Земли в метрах
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class OBDApp(toga.App):

    def startup(self):
        ###################################################
        # Перенес сюда , где контекст приложения уже создан


        ###################################################

        print('*' * 50, ELM327_ADDRESS)
        self.elm = ELM327()
        self.obd = OBDClient(self.elm)
        self.monitoring = False
        self.logger = setup_logging(self)
        self.logger.info("Приложение запущено")

        self.data_lock = threading.Lock()
        self.prev_point = None
        self.prev_time = None
        self.distance_m = 0.0

        self.error_label = toga.Label(
            "",
            style=Pack(text_align=CENTER, margin=8)
        )

        self.status_label = toga.Label(
            "Не подключено",
            style=Pack(text_align=CENTER, margin=8)
        )

        self.connect_btn = toga.Button(
#            "Подключиться к " + ELM327_ADDRESS,
            "Подкл. " + VERSION ,
            on_press=self.on_connect,
            style=Pack(margin=8)
        )

        self.speed_card, self.speed_label = self._make_card("Скорость", "— км/ч ")

        # В методе startup класса OBD2App
        self.speed_corr_input = toga.TextInput(
            value="1.0", 
            placeholder="Коэфф. скорости (напр. 1.05)",
            style=Pack(width=100, margin_left=5)
        )

        self.back_switch = toga.Switch(
            "Обр",
            value=False,
            on_change=self.on_back_toggle,
            style=Pack(margin_left=5)
        )

        # Добавьте его в один из ROW боксов
        speed_corr_box = toga.Box(
            children=[
                self.back_switch,
                toga.Label("Коррекция:", style=Pack(margin_right=5)),
                self.speed_corr_input,
            ],
            style=Pack(direction=ROW, margin=5)
        )        

        self.dist_card, self.dist_label = self._make_card("Расстояние", "— м ")


        self.clear_btn = toga.Button(
            "Сбр",
            on_press=self.on_clear_dist,
            #on_press=self.on_distance,
            style=Pack(margin=8)
        )
        self.clear_btn.enabled = True #False ivkin

        row1 = toga.Box(style=Pack(direction=ROW, margin=4))
        row1.add(self.speed_card)
        row1.add(speed_corr_box)

        row2 = toga.Box(style=Pack(direction=ROW, margin=4))
        row2.add(self.dist_card)
        row2.add(self.clear_btn)

        self.dist_full_card, self.dist_full_label = self._make_card("Итого", "— м ")
        self.clear_full_btn = toga.Button(
            "Сбр",
            on_press=self.on_clear_full_dist,
            style=Pack(margin=8)
        )
        self.clear_full_btn.enabled = True #False ivkin

        row3 = toga.Box(style=Pack(direction=ROW, margin=4))
        row3.add(self.dist_full_card)
        row3.add(self.clear_full_btn)


#########################################
# --- UI GPS---
#########################################
        self.lbl_gps_pos = toga.Label("Координаты: —", style=Pack(margin=10))
        self.lbl_gps_dist = toga.Label("Дистанция: 0.0 м", style=Pack(margin=10))
        self.lbl_gps_status = toga.Label("Готов", style=Pack(margin=10))
        row4 = toga.Box(style=Pack(direction=ROW, margin=4))
        row4.add(self.lbl_gps_pos)
        row4.add(self.lbl_gps_dist)
        row4.add(self.lbl_gps_status)
        
        # Выбор лимита скорости
        speed_values = [str(x) for x in range(10, 110, 10)]
        self.speed_limit = 10  # Переменная для хранения выбранного лимита
        self.speed_limit_select = toga.Selection(
            items=speed_values,
            on_change=self.on_speed_limit_change,
            style=Pack(width=100, margin_left=5)
        )        
        row5 = toga.Box(
            children=[
                toga.Label("Лимит скорости:", style=Pack(margin_right=5)),
                self.speed_limit_select
            ],
            style=Pack(direction=ROW, margin=4)
        )
        
########################################


        main_box = toga.Box(style=Pack(direction=COLUMN, margin=10))
        main_box.add(self.error_label)
        main_box.add(self.status_label)
        main_box.add(self.connect_btn)
        main_box.add(row1)
        main_box.add(row2)
        #main_box.add(self.clear_btn)

        main_box.add(row3)
        main_box.add(row4)
        main_box.add(row5)

        scroll = toga.ScrollContainer(
            content=main_box,
            horizontal=False,
            style=Pack(flex=1)
        )

        self.main_window = toga.MainWindow(title="OBD-II Monitor")
        self.main_window.content = scroll
        self.main_window.show()


        # Включение негаснущего экрана
        if JavaClass:
            try:
                # 128 - это значение WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                # Мы используем число напрямую, чтобы не импортировать лишние классы
                self._impl.native.getWindow().addFlags(128)
                self.logger.info("Android: Режим 'Экран всегда включен' активирован")
            except Exception as e:
                self.logger.error(f"Ошибка настройки экрана: {e}")


            '''
            Android агрессивно закрывает фоновые приложения. Чтобы этого избежать:
                Попросите пользователя в настройках телефона отключить «Оптимизацию батареи» для вашего приложения.
                Или добавьте запрос разрешения в код (требует ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).
            '''
            try:
                context = self._impl.native
                power_manager = context.getSystemService(context.POWER_SERVICE)
                # 1 = PowerManager.PARTIAL_WAKE_LOCK (экран может гаснуть, но CPU работает)
                self.wake_lock = power_manager.newWakeLock(1, "OBD2:DataCollection")
                self.wake_lock.acquire()
                self.logger.info("WakeLock активирован: CPU не уснет в фоне")
            except Exception as e:
                self.logger.error(f"Не удалось активировать WakeLock: {e}")

    ###################
            ## проверяю gps
            
            # Запуск фоновых задач через asyncio
            #asyncio.create_task(self.check_gps())            
            asyncio.create_task(self.check_status_gps())            
            #self.add_background_task(self.check_gps) 
    ###################




########################################################### GPS ###################################
########################################################### GPS ###################################
########################################################### GPS ###################################

    # ---------- обработчики ----------
    async def on_start(self, widget):
        """Запрос разрешения и старт трекинга."""
        try:
            # На некоторых платформах разрешение запрашивается интерактивно
            granted = await self.location.request_permission()
            if not granted:
                self.lbl_gps_status.text = "Нет разрешения на геолокацию"
                return

            # Опционально — фоновое отслеживание (iOS/Android)
            # await self.location.request_background_permission()

            self.location.on_change = self.on_location_update
            self.location.start_tracking()
            self.lbl_gps_status.text = "Трекинг запущен"
        except PermissionError:
            self.lbl_gps_status.text = "Доступ к GPS запрещён"
        except Exception as e:
            self.lbl_gps_status.text = f"Ошибка: {e}"

    def on_stop(self, widget):
        try:
            self.location.stop_tracking()
            self.lbl_gps_status.text = "Остановлено"
        except Exception as e:
            self.lbl_gps_status.text = f"Ошибка: {e}"

    def on_reset(self, widget):
        self.distance_m = 0.0
        self.prev_point = None
        self.prev_time = None
        self.lbl_gps_dist.text = "Дистанция: 0.0 м"

    def on_speed_limit_change(self, widget):
        """Обработчик изменения лимита скорости."""
        try:
            self.speed_limit = int(widget.value)
            self.logger.info(f"Установлен лимит скорости: {self.speed_limit}")
        except (ValueError, TypeError):
            pass

    def on_back_toggle(self, widget):
        """Обработчик переключения чекбокса коррекции."""
        status = "включена" if widget.value else "выключена"
        # Изменить цвет текста на красный
        if widget.value : self.dist_label.style.color = 'red'
        else : self.dist_label.style.color = 'black'
        
        
        self.logger.info(f"Коррекция скорости {status}")

    # ---------- колбэк обновления координат ----------
    def on_location_update(self, service, *, location, altitude, **kwargs):
        """
        location  — объект с .latitude/.longitude или .lat/.lng
        altitude  — высота в метрах (может быть None)
        """        
        # Пытаемся получить координаты из разных возможных атрибутов
        lat = getattr(location, 'latitude', getattr(location, 'lat', None))
        lon = getattr(location, 'longitude', getattr(location, 'lng', None))

        if lat is None or lon is None:
            self.logger.warning("Получены некорректные координаты GPS")
            return

        now = time.monotonic()        
        
        ''' ivkin !!!!
        if self.prev_point is not None:
            d = haversine_m(*self.prev_point, lat, lon)

            # Фильтр шума: GPS «дрожит» на месте. Игнорируем смещения < 2 м
            # и нереально большие прыжки (> 200 м/с ≈ 720 км/ч).
            if d >= 2.0:
                dt = now - self.prev_time if self.prev_time else 1
                if d / dt < 200:
                    self.distance_m += d
        '''

        self.prev_point = (lat, lon)
        self.prev_time = now

        self.lbl_gps_pos.text = f"Координаты: {lat:.6f}, {lon:.6f}"
        #ivkin self.lbl_gps_dist.text = f"Дистанция: {self.distance_m:.1f} м"

        self.logger.info(self.lbl_gps_pos.text)

#################################################
#################################################
#################################################

    def keep_screen_on(self):
        # Доступ к Android Activity через бэкенд Toga
        activity = self._impl.native
        WindowManager_LayoutParams = JavaClass("android/view/WindowManager$LayoutParams")
        activity.getWindow().addFlags(
            WindowManager_LayoutParams.FLAG_KEEP_SCREEN_ON
        )


    def _make_card(self, title: str, value: str):
        box = toga.Box(style=Pack(direction=COLUMN, margin=6, flex=1))
        box.add(toga.Label(title, style=Pack(text_align=CENTER, font_size=11)))
        lbl = toga.Label(value, style=Pack(text_align=CENTER, font_size=16))
        box.add(lbl)
        return box, lbl

    # ── Подключение ───────────────────────────────────────────────────────────

    def on_connect(self, widget):
        if self.elm.is_connected():
            self._monitoring = False
            self.elm.disconnect()
            self.status_label.text = "Отключено"
###########################
###########################
###########################
            
            self.connect_btn.text = "Подключиться " 
            self.clear_btn.enabled = True #False
        else:
            self.status_label.text = "Подключаюсь..."
            #time.sleep(3)
            #self.status_label.text = "Подключаюсь...2"

            self.error_label.text = ""
            self.connect_btn.enabled = False
            threading.Thread(target=self._connect_thread, daemon=True).start()

    def _connect_thread(self):
        """Фоновый поток — подключение к ELM327."""
        success = False
        error_msg = ""
        self.logger.info("Подключаюсь...")
###################
        # Используем run_coroutine_threadsafe для безопасного вызова из потока
        asyncio.run_coroutine_threadsafe(self.on_start(None), self.loop)
###################        #asyncio.create_task(self.on_start)
        #self.add_background_task(self.on_start) 
###################


        try:
            success = self.elm.connect()
        except Exception as e:
            error_msg = str(e)
            self.logger.error(error_msg)

        # Передаём результат в UI-поток
        asyncio.run_coroutine_threadsafe(
            self._on_connected_ui(success, error_msg),
            self.loop
        )

    async def _on_connected_ui(self, success: bool, error_msg: str = ""):
        self.connect_btn.enabled = True
        if success:            
            self.status_label.text = "Подключено к ELM327"
            self.connect_btn.text = "Отключиться"
            self.error_label.text = ""
            self.clear_btn.enabled = True
            self._monitoring = True
            
            try:
                corr = float(self.speed_corr_input.value)
            except ValueError:
                corr = 1.0  # Если ввели не число, используем 1.0
            self.koef = corr
            
            
            
            threading.Thread(target=self._monitor_loop, daemon=True).start()
        else:
            self.status_label.text = "Ошибка подключения"
            self.error_label.text = error_msg
            self.connect_btn.text = "Подключиться" #+ ELM327_ADDRESS

    # ── Мониторинг ────────────────────────────────────────────────────────────
    def _monitor_loop(self):
        """Фоновый поток — опрос данных """
        while self.elm.is_connected() and getattr(self, "_monitoring", False):
            try:
                # подждал изменения коэффициента
                with self.data_lock:
                    self.elm.measure_distance(1)
                # Обновление UI
                if self.loop and self.loop.is_running():
                    # если еще в рабочем потоке, те не зеакрыто приложение
                    asyncio.run_coroutine_threadsafe(
                        self._update_ui_async(),
                        self.loop
                    )
                else : break 
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    self._on_monitor_error(str(e)),
                    self.loop
                )
                break#            time.sleep(1.0)


    async def _update_ui_async(self):
    #def _update_ui_async(self):
        #self.koef = '1.5'
        try:
            corr = float(self.speed_corr_input.value)
        except ValueError:
            corr = 1.0  # Если ввели не число, используем 1.0
        self.koef = corr
        self.elm.back= self.back_switch.value
        
        self.speed_label.text = f"{self.elm.speed} - км/ч"
        self.dist_label.text = f"{int(float(self.elm.dist))}-м | корр.{int(float(self.elm.dist) * float(self.koef) )}-м" 
        self.dist_full_label.text = f"{int(float(self.elm.full_dist))}-м | корр.{int(float(self.elm.full_dist) * float(self.koef) )}-м" 

    async def _on_monitor_error(self, msg: str):
        self._monitoring = False
        self.status_label.text = "Соединение потеряно"
        self.error_label.text = msg
        self.connect_btn.text = "Подключиться к WiFi"
        #self.clear_btn.enabled = True #False ivkin
    # ── DTC ───────────────────────────────────────────────────────────────────

    def on_clear_dist(self, widget):
# В UI-потоке (запись)
        with self.data_lock:
            self.obd.elm.dist = 0
            self.obd.dist = 0
            asyncio.run_coroutine_threadsafe(
                self._update_ui_async(),
                self.loop
            )

    def on_clear_full_dist(self, widget):
# В UI-потоке (запись)
        with self.data_lock:
            self.obd.elm.dist = 0
            self.obd.elm.full_dist = 0
            self.obd.dist = 0
            asyncio.run_coroutine_threadsafe(
                self._update_ui_async(),
                self.loop
            )

    async def check_status_gps(self, widget=None):
        try:
            while True :
                # Небольшая пауза, чтобы UI успел прогрузиться
                await asyncio.sleep(1.0)
                self.logger.info("Запрос разрешений GPS...")
                # Запрашиваем только основные разрешения
                granted = await self.location.request_permission()
                self.logger.info(f"Результат запроса GPS: {granted}")
                
                if granted:
                    self.logger.info("-------Разрешение получено, запускаем трекинг")
                    self.lbl_gps_status.text = "---GPS: OK"
                else:
                    self.logger.error("Разрешение GPS отклонено")
                    self.lbl_gps_status.text = "GPS: Отказ"
                
        except Exception as e:
            self.logger.error(f"Критическая ошибка GPS: {e}")
            self.lbl_gps_status.text = "GPS: Ошибка"




    async def check_gps(self, widget=None):
        try:
            # Небольшая пауза, чтобы UI успел прогрузиться
            await asyncio.sleep(1.0)
            self.logger.info("Запрос разрешений GPS...")
            # Запрашиваем только основные разрешения
            granted = await self.location.request_permission()
            self.logger.info(f"Результат запроса GPS: {granted}")
            
            if granted:
                self.logger.info("Разрешение получено, запускаем трекинг")
                self.location.on_change = self.on_location_update
                self.location.start_tracking()
                self.lbl_gps_status.text = "GPS: OK"
                
                # Запускаем отдельный процесс мониторинга доступности через run_coroutine_threadsafe
                #asyncio.run_coroutine_threadsafe(self.monitor_gps_status(), self.loop)                
                asyncio.run_coroutine_threadsafe(self.monitor_gps_status(), self.loop)

                
                while True:                    # Система сама вызывает on_location_update при изменении координат.
                    await asyncio.sleep(1.0)
            else:
                self.logger.error("Разрешение GPS отклонено")
                self.lbl_gps_status.text = "GPS: Отказ"
                
        except Exception as e:
            self.logger.error(f"Критическая ошибка GPS: {e}")
            self.lbl_gps_status.text = "GPS: Ошибка"

    async def monitor_gps_status(self):
        """Отдельный процесс проверки доступности и активности GPS."""
        while True:
            await asyncio.sleep(5.0)  # Проверка каждые 5 секунд
            now = time.monotonic()
            
            # Если данные не обновлялись более 10 секунд
            if self.prev_time and (now - self.prev_time > 10.0):
                self.lbl_gps_status.text = "GPS: Сигнал потерян"
                # self.lbl_gps_status.style.color = "red" # Toga style update
            elif self.prev_time:
                self.lbl_gps_status.text = "GPS: OK"
                # self.lbl_gps_status.style.color = "green"
def main():
    return OBDApp("OBD-II Monitor", "com.example.obd2")