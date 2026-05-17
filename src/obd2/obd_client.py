from obd2.elm327 import ELM327


def _parse_hex(response: str) -> list[int]:
    """Извлечь байты из ответа ELM327."""
    clean = response.replace("\r", " ").replace("\n", " ")
    parts = []
    for token in clean.split():
        try:
            if len(token) == 2:
                parts.append(int(token, 16))
        except ValueError:
            pass
    return parts


class OBDClient:
    def __init__(self, elm: ELM327):
        self.elm = elm
        self.dist = 0 
        self.full_dist = 0 
        self.speed = 0 


    def get_speed(self) -> int | None:
        """Скорость км/ч. PID 010D."""
        self.speed = self.elm.speed

    def get_dist(self) -> int | None:
        self.dist = self.elm.dist

    def clear_dist(self):
        self.elm.dist = 0
        self.dist = 0 
