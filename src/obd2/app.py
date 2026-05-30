VERSION = "1"

"""
Чтение OBDII

"""

import asyncio
import math
import threading
import time
import toga

from datetime import timedelta
from toga.sources import ListSource
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

    #####################################
    #####################################
    #data_lock = threading.Lock()
    #####################################
    #####################################


    def startup(self):
        ###################################################
        # Перенес сюда , где контекст приложения уже создан


        ###################################################

        #print('*' * 50, ELM327_ADDRESS)


########################################
        self.data = []
        # ListSource для таблицы — обновляет только изменившиеся строки, без перестройки
        self.table_source = ListSource(
            accessors=["n", "lim", "dist_m", "sec", "prc"],
            data=[]
        )
        self.elm = ELM327()
        
        self.obd = OBDClient(self.elm, data = self.data )

        self.monitoring = False
        self.logger = setup_logging(self)
        self.logger.info("Приложение запущено")

        self.prev_point = None
        self.prev_time = None
        self.distance_m = 0.0
        self.total_time_sec = 0
        self.elapsed = 0
        self._beep_active = False   # антидребезг: True пока сигнал уже играет
        self.koef = 1.0             # коэффициент коррекции скорости (до подключения = 1.0)

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
            "Вкл " + VERSION ,
            on_press=self.on_connect,
            style=Pack(margin=4)
        )

        self._sw_running = False
        self._sw_start = None
        self._sw_elapsed = 0.0

        self.stopwatch_btn = toga.Button(
            "СМ",
            on_press=self.on_stopwatch_toggle,
            style=Pack(margin=4)
        )
        self.stopwatch_label = toga.Label(
            "0.0 с",
            style=Pack(text_align=CENTER, margin=4, font_size=12)
        )

        row0 = toga.Box(style=Pack(direction=ROW, margin=4))
        row0.add(self.connect_btn)
        row0.add(self.stopwatch_btn)
        row0.add(self.stopwatch_label)
        row0.add(self.status_label)



        #self.speed_card, self.speed_label = self._make_card("Скорость", "— км/ч ")
        self.speed_label = toga.Label("— км/ч ", style=Pack(text_align=CENTER, font_size=12))


        # В методе startup класса OBD2App
        self.speed_corr_input = toga.TextInput(
            value="1.0", 
            placeholder="Коэфф.",
            style=Pack(width=70, margin_left=5)
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
                toga.Label("Корр:", style=Pack(margin_right=5)),
                self.speed_corr_input,
            ],
            style=Pack(direction=ROW, margin=5)
        )        

        #self.dist_card, self.dist_label = self._make_card("Расстояние", "— м ")
        self.dist_label = toga.Label("— м ", style=Pack(text_align=CENTER, font_size=12))


        self.clear_btn = toga.Button(
            "Сб",
            on_press=self.on_clear_dist,
            #on_press=self.on_distance,
            style=Pack(margin=4)
        )
        self.clear_btn.enabled = True #False ivkin
        self.total_time_sec_label = toga.Label("— sec", style=Pack(text_align=CENTER, font_size=12))
        #self.total_time_sec = 0




        row1 = toga.Box(style=Pack(direction=ROW, margin=4))
        #row1.add(self.speed_card)
        row1.add(self.speed_label)
        row1.add(speed_corr_box)

        row2 = toga.Box(style=Pack(direction=ROW, margin=4))
        row2.add(self.dist_label)
        row2.add(self.clear_btn)
        row2.add(self.total_time_sec_label)
        
        
        

        #self.dist_full_card, self.dist_full_label = self._make_card("Итого", "— м ")
        self.dist_full_label = toga.Label("— м ", style=Pack(text_align=CENTER, font_size=12))
        
        
        self.clear_full_btn = toga.Button(
            "Сб",
            on_press=self.on_clear_full_dist,
            style=Pack(margin=4)
        )
        self.clear_full_btn.enabled = True #False ivkin
        self.delta_time_sec_label = toga.Label("— sec", style=Pack(text_align=CENTER, font_size=12))


        row3 = toga.Box(style=Pack(direction=ROW, margin=4))
        row3.add(self.dist_full_label)
        row3.add(self.clear_full_btn)
        row3.add(self.delta_time_sec_label)    # время отставания


        '''
#########################################
# --- UI GPS---
#########################################
        self.lbl_gps_pos = toga.Label("Коор: ", style=Pack(margin=10))
        self.lbl_gps_dist = toga.Label("Дист: 0.0 м", style=Pack(margin=10))
        self.lbl_gps_status = toga.Label("Готов", style=Pack(margin=10))
        row4 = toga.Box(style=Pack(direction=ROW, margin=4))
        row4.add(self.lbl_gps_pos)
        row4.add(self.lbl_gps_dist)
        row4.add(self.lbl_gps_status)
        '''
        
        # Выбор лимита скорости
        speed_values = [str(x) for x in range(10, 110, 10)]
        self.speed_limit = 10  # Переменная для хранения выбранного лимита
        self.speed_limit_select = toga.Selection(
            items=speed_values,
            on_change=self.on_speed_limit_change,
            style=Pack(width=100, margin_left=5)
        )        
        # Выбор процента скорости
        prc_values = [str(x) for x in range(100, 40, -5)]
        self.prc = 100  # Переменная для хранения процента
        self.prc_limit = toga.Selection(
            items=prc_values,
            on_change=self.on_prc_limit_change,
            style=Pack(width=100, margin_left=5)
        )        

        row5 = toga.Box(
            children=[
                toga.Label("Лимит скорости:", style=Pack(margin_right=5)),
                self.speed_limit_select,
                self.prc_limit
            ],
            style=Pack(direction=ROW, margin=4)
        )



        self.obd_table = toga.Table(
            columns=["N", "Лим","Дист(м)","Сек","Прц"],
            data= self.data,
            style=Pack(flex=1, margin=5)
        )

        main_box = toga.Box(style=Pack(direction=COLUMN, flex=1, margin=5))
        #main_box.add(self.error_label)
        #main_box.add(self.status_label)
        #main_box.add(self.connect_btn)
        
        main_box.add(row0)
        
        

        main_box.add(row2) # малая дистанция
        main_box.add(row3) # общая дистанция

        #######################################################
        # main_box.add(row4) пока не показываю координаты !!!!!!!!!
        #######################################################


        main_box.add(row1)   # скорость и коррекция



        main_box.add(row5)   # лимит скорости 
        main_box.add(self.obd_table)


        scroll = toga.ScrollContainer(
            content=main_box,
            horizontal=False,
            style=Pack(flex=1)
        )



        self.main_window = toga.MainWindow(title="OBD-II Monitor")
        #self.main_window.content = main_box
        self.main_window.content = scroll
        self.main_window.show()

        #asyncio.run_coroutine_threadsafe(
        #    self._stopwatch_loop
        #)        
        asyncio.create_task(self._stopwatch_loop())


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


########################################################### GPS ###################################
########################################################### GPS ###################################
########################################################### GPS ###################################
    ###################
            ## проверяю gps
            
            # Запуск фоновых задач через asyncio
            #asyncio.create_task(self.check_gps())            
            #asyncio.create_task(self.check_status_gps())            
            #asyncio.create_task(self.check_gps())
    ###################

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


    def on_prc_limit_change(self, widget):
        self.prc = int(widget.value)
        

    def on_speed_limit_change(self, widget):
        """Обработчик изменения лимита скорости."""
        try:
                        
            #self.beep()              # 1000 Гц, 300 мс — стандартный сигнал
            #self.beep(1200, 200)     # короткий высокий — предупреждение
            #self.beep(600, 800)      # длинный низкий — ошибка/отключение            

            self.speed_limit = int(widget.value)
            self.logger.info(f"Установлен лимит скорости: {self.speed_limit}")
            
            #print('-==-1'*10, data_lock)
            with data_lock:
#######################################################################################
#######################################################################################
#######################################################################################
#######################################################################################
#######################################################################################
#######################################################################################

                #self.table_add_row("л ", self.speed_limit, f"{round(float(self.elm.dist))}")    
                if (len(self.data) == 0 ) :       
                    self.data.insert(0, [ 1, self.speed_limit, 0 , 0 , self.prc])    # Работает так -------------
                else :
                    cur_m_speed = round(self.data[0][1])/3.6  # скорость м/сек
                    prc = self.data[0][4]                   # процент скорости
                    dist = self.elm.dist * self.koef        # метры с учетом коэффициента
                    time = dist / (cur_m_speed * prc / 100 )
                    self.data[0][2] = round(float(dist))
                    self.data[0][3] = round(float(time))
                    self.data.insert(0,[ len(self.data) + 1, self.speed_limit, 0 , 0, self.prc])    
                    
                #self.data.insert(0,( self.speed_limit, "0" , "0" ))    
                self.obd_table.data = self.data  # обновляет таблицу    
                self.obd_table.refresh()
                self.obd.elm.dist = 0
                self.obd.dist = 0
                ##############################################
                asyncio.run_coroutine_threadsafe(       #
                    self._update_ui_async(),            #   
                    self.loop                           #
                )        
            #self.elm.dist = 0                # сбросил в 0 
            #print(self.data)
            
        except (ValueError, TypeError) as e:
            error_msg = str(e)
            self.logger.error(error_msg)
            print(error_msg)
            pass

    def on_back_toggle(self, widget):
        """Обработчик переключения чекбокса коррекции."""
        status = "включена" if widget.value else "выключена"
        # Изменить цвет текста на красный
        if widget.value : self.dist_label.style.color = 'red'
        else : self.dist_label.style.color = 'black'
        
        
        self.logger.info(f"Коррекция скорости {status}")

    def on_stopwatch_toggle(self, widget):
        if self._sw_running:
            self._sw_elapsed += time.monotonic() - self._sw_start
            self._sw_start = None
            self._sw_running = False
            self.stopwatch_btn.text = "СМ"
        else:
            self._sw_start = time.monotonic()
            self._sw_running = True
            self.stopwatch_btn.text = "Стоп"

    def time_format(self, seconds: float) -> str:
        #m = round(seconds) // 60
        #s = seconds % 60
        #return f"{m}:{s:04.1f}" if m > 0 else f"{s:.1f} с"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"        
        #str(timedelta(seconds=3725))  # → "1:02:05"
        

    async def _stopwatch_loop(self, widget=None):
        while True:
            await asyncio.sleep(0.1)
            if self._sw_running:
                elapsed = self._sw_elapsed + (time.monotonic() - self._sw_start)
            else:
                elapsed = self._sw_elapsed
            self.stopwatch_label.text = self.time_format(elapsed)
            self.elapsed = elapsed

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

    def beep(self, freq=600, duration_ms=500, sec_sleep = 1):
        """Звуковой сигнал в отдельном потоке — не блокирует UI.
        По завершении сбрасывает _beep_active, разрешая следующий сигнал.
        звучать каждый count раз
        """
        def _play():
            try:
                if JavaClass:
                    ToneGenerator = JavaClass("android/media/ToneGenerator")
                    AudioManager  = JavaClass("android/media/AudioManager")
                    tg = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 100)
                    tg.startTone(ToneGenerator.TONE_PROP_BEEP, duration_ms)
                    #time.sleep(duration_ms / 1000)
                    time.sleep(sec_sleep)
                else:
                    import winsound
                    winsound.Beep(freq, duration_ms)
                    time.sleep(sec_sleep)
            except Exception as e:
                self.logger.warning(f"beep: {e}")
            finally:
                self._beep_active = False   # готов к следующему сигналу

        if not self._beep_active:
            self._beep_active = True
            threading.Thread(target=_play, daemon=True).start()

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
            
            self.connect_btn.text = "Вкл" 
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
            self.status_label.text = "OK"
            self.connect_btn.text = "Выкл"
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
            self.status_label.text = "Ошибка"
            self.error_label.text = error_msg
            self.connect_btn.text = "Вкл" #+ ELM327_ADDRESS

    # ── Мониторинг ────────────────────────────────────────────────────────────
    def _monitor_loop(self):
        """Фоновый поток — опрос данных """
        while self.elm.is_connected() and getattr(self, "_monitoring", False):
            try:
                # подждал изменения коэффициента
                with data_lock:
                    self.elm.measure_distance(1)
                ###################################################    
                # Обновление UI
                if self.loop and self.loop.is_running():
                    # если еще в рабочем потоке, те не зеакрыто приложение
                    asyncio.run_coroutine_threadsafe(
                        self._update_ui_async(),
                        self.loop
                    )
                    asyncio.run_coroutine_threadsafe(
                        self._on_ref_table(),
                        self.loop
                    )
                    
                else : break 
            
                
                ##################################################
                
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    self._on_monitor_error(str(e)),
                    self.loop
                )
                print(str(e))
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

        #lat_text = self.lbl_gps_pos.text.replace("Координаты: ", "")
        #lat, lon = (lat_text.split(", ") + ["—", "—"])[:2] if "," in lat_text else ("—", "—")
        
        #########################################################################################
        #########################################################################################
        #########################################################################################
        #########################################################################################
        ########### Пересчитываю времена
        tot_sec = 0

        dist = round(self.elm.dist * self.koef )       # метры с учетом коэффициента

        #print('-==-0000',dist, self.data)
        
        if len(self.data) > 0 :
            for item in self.data:
                tot_sec += int(item[3])
                
            cur_m_speed = round(self.data[0][1])/3.6  # скорость м/сек
            prc = self.data[0][4]                   # процент скорости
            tot_sec += dist / (cur_m_speed * prc / 100 )
            ########## подчищаю историю
            #print('-==-0',dist, self.data)
            if dist < 0 : ## Дощли до стартовой точки пути который откатываем назад
                #print('-==-1',dist, self.data)
                if len(self.data) > 0 :
                    # удалил последний участок в текущем пути
                    del self.data[0]
                    if len(self.data) > 0 :
                        dist_0 = round(self.data[0][2])
                        dist_0 += dist
                        self.data[0][2] = dist_0                    # удалил остаток из нового
                        dist = round(self.data[0][2] / self.koef)   # обновил в таблице   
                        # обязательно с блокировкой 
                        with data_lock:
                            self.elm.dist  = dist                       # сохранил как текущее + учел коэффициент
                            self.obd.dist = dist
                    else :
                        # Отключаюсь
                        self._monitoring = False
                        self.elm.disconnect()
                        self.status_label.text = "Отключено"
                        self.connect_btn.text = "Вкл" 
                        self.clear_btn.enabled = True #False
                        
        self.speed_label.text = f"{self.elm.speed} - км/ч"
        self.dist_label.text = f"{round(self.elm.dist)}-м | кр.{round(dist)}"
        self.dist_full_label.text = f"{round(self.elm.full_dist)}-м | кр.{round(self.elm.full_dist * self.koef)}"

        self.total_time_sec_label.text = f"{self.time_format(round(float(tot_sec)))}"
        delta_sec = round(float((tot_sec - self.elapsed )))  # расчетное время минус физическое
        #print(f"{tot_sec} - {self.elapsed}")
        self.delta_time_sec_label.text = f"{delta_sec}-сек" # время опоздания
        if delta_sec < 0:   # опаздываем
            self.delta_time_sec_label.style.color = 'red'
            self.beep(600, 1000, 5)    # сигнал раз за раз, не каждую секунду
        else:
            self.delta_time_sec_label.style.color = 'green'
            self._beep_active = False   # сбросить флаг когда перестали опаздывать


        # Принудительное обновление таблицы — Toga не отслеживает мутации списка
        self.obd_table.data = self.data
        self.obd_table.refresh()        #######################
        
        #########################################################################################
        #########################################################################################

    async def _on_ref_table(self):
        self.obd_table.refresh()    

    async def _on_monitor_error(self, msg: str):
        self._monitoring = False
        self.status_label.text = "Соединение потеряно"
        self.error_label.text = msg
        self.connect_btn.text = "Вкл"
        #self.clear_btn.enabled = True #False ivkin
    # ── DTC ───────────────────────────────────────────────────────────────────

    def on_clear_dist(self, widget):
# В UI-потоке (запись)
        with data_lock:
            self.obd.elm.dist = 0
            self.obd.dist = 0
            asyncio.run_coroutine_threadsafe(
                self._update_ui_async(),
                self.loop
            )

    def on_clear_full_dist(self, widget):
# В UI-потоке (запись)
        with data_lock:
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