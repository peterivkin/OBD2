#import obd


import socket
import threading
import time

import logging
from pathlib import Path
####################################################################
ELM_SLEEP = 0.05    ################################################
####################################################################

IS_BLUETOOTH = False #True    ####################################

ELM_IP = "192.168.0.10"
#ELM_IP = "127.0.0.1"
ELM_PORT = 35000

################################
################################
ELM327_ADDRESS = "73:2F:24:40:CD:D3"  # BROM
#ELM327_ADDRESS = "74:1E:B1:3A:42:65"   # Планшет
#ELM327_ADDRESS = "40:45:DA:69:4C:A8"   # Телефон
#ELM_IP = ELM327_ADDRESS
#ELM_PORT = 1
################################
################################

LOG_FILE = "/storage/emulated/0/Download/app2.log"



def setup_logging(app=None):

    #log_dir = Path(PATH)
    #log_dir = Path(app.paths.data)
    #log_dir.mkdir(parents=True, exist_ok=True)
    #log_file = LOG_FILE #log_dir / "app3.log"

    logger = logging.getLogger("myapp")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.file = LOG_FILE
    print(f"---LOGFILE-{logger.file}")


    if not logger.handlers:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    return logger





class ELM327:
    #dist = 0 
    def __init__(self, ip=ELM_IP, port=ELM_PORT):
        self.ip = ip
        self.port = port
        self._sock = None
        
        self.lock = threading.Lock()
        self.last_error = ""  # ← вместо глобальной ERROR
        
        self.logger = setup_logging(self)
        self.speed = 0
        self.cur_speed = 0
        self.cur_time = time.monotonic()
        self.dist = 0
        self.full_dist = 0
        

    def connect(self, timeout: float = 5.0) -> bool:
        # Закрываем старый сокет, если он был открыт
        if self._sock:
            self.close()

       # Проверяем, является ли адрес Bluetooth MAC-адресом (например, 00:11:22:33:44:55)
        is_bluetooth = ":" in self.ip and len(self.ip) == 17
        is_bluetooth = IS_BLUETOOTH
        
        try:
            if is_bluetooth:
                # Подключение по Bluetooth (RFCOMM)
                # AF_BLUETOOTH доступен в Python на Linux/Android
                # Протокол RFCOMM обычно использует порт 1
                self.logger.info(f"Попытка Bluetooth подключения к {self.ip} порт ... {self.port}")
                self._sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
                self._sock.settimeout(timeout)
                self._sock.connect((self.ip, self.port))
            else:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.settimeout(timeout)
                self.logger.info(f"Подключаюсь к {self.ip}:{self.port}...")
                try:
                    self._sock.connect((self.ip, self.port))
                except Exception as e:
                    self.last_error = f"Ошибка подключения к {self.ip}:{self.port} - {e} !!!"
                    self.logger.error(self.last_error)
                    return False
                #self._sock = sock          # присваиваем только после успешного connect             
            self._sock.setblocking(True)    # под вопросом , надо ли блокировать чтение ??????
        except Exception as e:
            self.logger.error(f"Ошибка подключения к {self.ip}: {e}")
            self.close()
            return False



        self.logger.info("Подключился.")
        self.init() # инициализировал быстрый опрос
        return True

    def send(self, cmd: str) -> str:
        """Отправить AT- или OBD-команду, вернуть очищенный ответ."""
        if not self._sock:
            return ""
        try:
            self._sock.sendall((cmd + "\r").encode())
            #self.logger.info(f"Отправил - |{cmd}")
            data = b""
            # ELM327 завершает ответ символом '>'
            while b">" not in data:
                chunk = self._sock.recv(1024)
                if not chunk:
                    break
                data += chunk
            #recv = data.decode(errors="ignore").replace("\r", " ").replace(">", "").strip()
            recv = data.decode(errors="ignore").replace("\r", "").replace(">", "").strip()
            #self.logger.info(f"Получил - |{recv}")       
            return recv
        except Exception as e:
            self.logger.error(f"Ошибка при передаче данных: {e}")
            return ""
    def init(self):
        """Инициализация адаптера."""
        for cmd in ["ATZ", "ATE0", "ATL0", "ATS0", "ATH0", "ATSP0"]:
            self.send(cmd)
            time.sleep(0.1)
        # Прогреем протокол запросом скорости
        self.send("010D")


    def read_speed_kmh(self):
        """Прочитать текущую скорость в км/ч (PID 010D). None при ошибке."""
        resp = self.send("010D")
        # Удаляем пробелы для надежности парсинга
        parts = str(resp).replace(" ", "")
        #self.speed = None
        try:
            if "410D" in parts:
                i = parts.index("410D")
                # Берем ровно 2 символа после 410D (байт скорости)
                hex_val = parts[i + 4 : i + 6]
                self.speed = int(hex_val, 16)
            else:
                self.logger.info(f'###########{parts}###########')
                #если пришло что-то не то
                #скорость не меняю , оставляю старую - self.speed
        except (ValueError, IndexError):
            pass
        return self.speed

    def close(self):
        if self._sock:
            self.close_sock(self._sock)
            self._sock = None

    def disconnect(self):
        self.close()

    def is_connected(self) -> bool:
        return self._sock is not None
    # ── Внутренние методы ─────────────────────────────────────────────────────

    def close_sock(self, sock):
        """Безопасно закрыть сокет."""
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass

        

#    async def measure_distance(self, duration_sec=None):
    def measure_distance(self, duration_sec=None):
        """
        Считает пройденную дистанцию методом трапеций.
        duration_sec=None - до Ctrl+C.
        Возвращает дистанцию в метрах.
        """
        #elm = ELM327()
        #self.init() ivkin

        distance_m = self.dist
        f_distance_m = self.full_dist
        #prev_speed_ms = None       # м/с
        #prev_t = None              # с
        prev_speed_ms = self.cur_speed     # м/с восстановил предыдущую скорость
        prev_t = self.cur_time             # с   восстановил предыдущее время, когда была эта скорость 
        t_start = time.monotonic()         # фиксировал время начала измерения

        try:
            while True:
                now = time.monotonic()
                speed_kmh = self.read_speed_kmh()
                time.sleep(ELM_SLEEP) # притормозил адаптер
                speed_ms = None
                if speed_kmh is not None:
                    speed_ms = speed_kmh / 3.6  # км/ч -> м/с

                    if prev_speed_ms is not None:
                        dt = now - prev_t
                        # Метод трапеций: усредняем соседние замеры
                        avg_ms = (prev_speed_ms + speed_ms) / 2
                        distance_m += avg_ms * dt
                        f_distance_m += avg_ms * dt

                    prev_speed_ms = speed_ms
                    prev_t = now
                    elapsed = now - t_start

                    self.speed = speed_kmh
                    self.dist = distance_m
                    self.full_dist = f_distance_m
                    
                    my_str = f"t={elapsed:6.1f}s  v={speed_kmh:3d} км/ч  S={distance_m:8.1f} м"
                    #print(my_str)
                    #self.logger.info(my_str)

                if duration_sec and (now - t_start) >= duration_sec:
                    self.cur_speed = speed_ms
                    self.cur_time = now
                    break

        except KeyboardInterrupt:
            pass
        finally:
            pass
            #self.close() ivkin

        return distance_m
        
 




    def query(self, pid: str) -> str:
        """Запрос OBD-II PID, возвращает сырой ответ."""
        return self.send(pid)
 
    

if __name__ == "__main__":
    elm = ELM327()
    if elm.connect() : 
        total = elm.measure_distance(duration_sec=10)
        print(f"\nИтого пройдено: {total:.1f} м ({total/1000:.3f} км)")
    else :
        print("Ошибка коннекта.")