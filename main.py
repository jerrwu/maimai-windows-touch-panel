from win32api import GetSystemMetrics
from PIL import Image
import math
import os
import queue
import sys
import time
import yaml
import serial
import win32api
import win32con
import win32gui
import win32print
import threading
import copy

# 是否开启调试模式
DEBUG = False
# 是否使用虚拟外键
EMU_BTN = True
# 编辑好的图片路径
IMAGE_PATH = "./image/image_monitor.png"
# 串口号
COM_PORT = "COM33"
# 比特率
COM_BAUDRATE = 9600
# 检测区域的像素值范围
AREA_SCOPE = 120
# 检测区域圆上点的数量
AREA_POINT_NUM = 8
# 是否开启屏幕反转
REVERSE_MONITOR = False
# touch_thread 是否启用sleep, 默认开启, 如果程序 CPU 占用较高则开启, 如果滑动时延迟极大请关闭
TOUCH_THREAD_SLEEP_MODE = False
# 每次 sleep 的延迟, 单位: 微秒, 默认 10 微秒
TOUCH_THREAD_SLEEP_DELAY = 10
# 窗口图标路径
icon_path = './image/favicon.ico'

exp_list = [
    ["A1", "A2", "A3", "A4", "A5", ],
    ["A6", "A7", "A8", "B1", "B2", ],
    ["B3", "B4", "B5", "B6", "B7", ],
    ["B8", "C1", "C2", "D1", "D2", ],
    ["D3", "D4", "D5", "D6", "D7", ],
    ["D8", "E1", "E2", "E3", "E4", ],
    ["E5", "E6", "E7", "E8", ],
]
exp_image_dict = {'41-65-93': 'A1', '87-152-13': 'A2', '213-109-81': 'A3', '23-222-55': 'A4', '69-203-71': 'A5',
                  '147-253-55': 'A6', '77-19-35': 'A7', '159-109-79': 'A8', '87-217-111': 'B1', '149-95-154': 'B2',
                  '97-233-9': 'B3', '159-27-222': 'B4', '152-173-186': 'B5', '192-185-149': 'B6', '158-45-23': 'B7',
                  '197-158-219': 'B8', '127-144-79': 'C1', '242-41-155': 'C2', '69-67-213': 'D1', '105-25-130': 'D2',
                  '17-39-170': 'D3', '97-103-203': 'D4', '113-25-77': 'D5', '21-21-140': 'D6', '155-179-166': 'D7',
                  '55-181-134': 'D8', '61-33-27': 'E1', '51-91-95': 'E2', '143-227-63': 'E3', '216-67-226': 'E4',
                  '202-181-245': 'E5', '99-11-183': 'E6', '75-119-224': 'E7', '182-19-85': 'E8'}


class SerialManager:
    def __init__(self):
        self.p1Serial = serial.Serial(COM_PORT, COM_BAUDRATE)
        self.settingPacket = bytearray([40, 0, 0, 0, 0, 41])
        self.startUp = False
        self.recvData = ""
        self.touchQueue = queue.Queue()
        self.data_lock = threading.Lock()
        self.touchThread = threading.Thread(target=self.touch_thread)
        self.writeThread = threading.Thread(target=self.write_thread)
        self.now_touch_data = b''
        self.now_touch_keys = []
        self.ping_touch_thread()

    def start(self):
        print(f"开始监听 {COM_PORT} 串口...")
        self.touchThread.start()
        self.writeThread.start()

    def ping_touch_thread(self):
        self.touchQueue.put([self.build_touch_package(exp_list), []])

    def touch_thread(self):
        while True:
            start_time = time.perf_counter()
            if self.p1Serial.is_open:
                self.read_data(self.p1Serial)
            if not self.touchQueue.empty():
                # print("touchQueue 不为空，开始执行")
                s_temp = self.touchQueue.get()
                self.update_touch(s_temp)
            # 延迟防止消耗 CPU 时间过长
            if TOUCH_THREAD_SLEEP_MODE:
                microsecond_sleep(TOUCH_THREAD_SLEEP_DELAY)
            # print("单次执行时间:", (time.perf_counter() - start_time) * 1e3, "毫秒")

    def write_thread(self):
        while True:
            # # 延迟匹配波特率
            # time.sleep(0.0075)  # 9600
            # # time.sleep(0.002)  # 115200
            time.sleep(0.000001)  # 避免延迟过大
            if not self.startUp:
                # print("当前没有启动")
                continue
            # print(self.now_touch_data)
            with self.data_lock:
                self.send_touch(self.p1Serial, self.now_touch_data)

    def destroy(self):
        self.touchThread.join()
        self.p1Serial.close()

    def read_data(self, ser):
        if ser.in_waiting == 6:
            self.recvData = ser.read(6).decode()
            # print(self.recvData)
            self.touch_setup(ser, self.recvData)

    def touch_setup(self, ser, data):
        byte_data = ord(data[3])
        if byte_data in [76, 69]:
            self.startUp = False
        elif byte_data in [114, 107]:
            for i in range(1, 5):
                self.settingPacket[i] = ord(data[i])
            ser.write(self.settingPacket)
        elif byte_data == 65:
            self.startUp = True
            print("已连接到游戏")

    def send_touch(self, ser, data):
        ser.write(data)

    # def build_touch_package(self, sl):
    #     sum_list = [0, 0, 0, 0, 0, 0, 0]
    #     for i in range(len(sl)):
    #         for j in range(len(sl[i])):
    #             if sl[i][j] == 1:
    #                 sum_list[i] += (2 ** j)
    #     s = "28 "
    #     for i in sum_list:
    #         s += hex(i)[2:].zfill(2).upper() + " "
    #     s += "29"
    #     # print(s)
    #     return bytes.fromhex(s)

    def build_touch_package(self, sl):
        sum_list = [sum(2 ** j for j, val in enumerate(row) if val == 1) for row in sl]
        hex_list = [hex(i)[2:].zfill(2).upper() for i in sum_list]
        s = "28 " + " ".join(hex_list) + " 29"
        # print(s)
        return bytes.fromhex(s)

    def update_touch(self, s_temp):
        # if not self.startUp:
        #     print("当前没有启动")
        #     return
        with self.data_lock:
            self.now_touch_data = s_temp[0]
            self.send_touch(self.p1Serial, s_temp[0])
            self.now_touch_keys = s_temp[1]
        if DEBUG: 
            print("Touch Keys:", s_temp[1])
        # else:
        #     self.send_touch(self.p2Serial, s_temp[0])

    def change_touch(self, sl, touch_keys):
        self.touchQueue.put([self.build_touch_package(sl), touch_keys])


def restart_script():
    python = sys.executable
    script = os.path.abspath(sys.argv[0])
    os.execv(python, [python, script])


def microsecond_sleep(sleep_time):
    # time.sleep(sleep_time / 1000000)
    end_time = time.perf_counter() + (sleep_time - 1.0) / 1e6  # 1.0是时间补偿，需要根据自己PC的性能去实测
    while time.perf_counter() < end_time:
        pass


def get_colors_in_area(x, y):
    colors = set()  # 使用集合来存储颜色值，以避免重复
    num_points = AREA_POINT_NUM  # 要获取的点的数量
    angle_increment = 360.0 / num_points  # 角度增量
    cos_values = [math.cos(math.radians(i * angle_increment)) for i in range(num_points)]
    sin_values = [math.sin(math.radians(i * angle_increment)) for i in range(num_points)]
    # 处理中心点
    if 0 <= x < exp_image_width and 0 <= y < exp_image_height:
        colors.add(get_color_name(exp_image.getpixel((x, y))))
    # 处理圆上的点
    for i in range(num_points):
        dx = int(AREA_SCOPE * cos_values[i])
        dy = int(AREA_SCOPE * sin_values[i])
        px = x + dx
        py = y + dy
        if 0 <= px < exp_image_width and 0 <= py < exp_image_height:
            colors.add(get_color_name(exp_image.getpixel((px, py))))
    return list(colors)


def get_color_name(pixel):
    return str(pixel[0]) + "-" + str(pixel[1]) + "-" + str(pixel[2])


# def convert(touch_data):
#     copy_exp_list = copy.deepcopy(exp_list)
#     touch_data_values = list(touch_data.values())
#     touch_keys = set()
#     touched = 0
#     for i in touch_data_values:
#         touched += 1
#         x = i["x"]
#         y = i["y"]
#         for rgb_str in get_colors_in_area(x, y):
#             if not rgb_str in exp_image_dict:
#                 continue
#             touch_keys.add(exp_image_dict[rgb_str])
#     # print("Touched:", touched)
#     # print("Touch Keys:", touch_keys)
#     touch_keys_list = list(touch_keys)
#     for i in range(len(copy_exp_list)):
#         for j in range(len(copy_exp_list[i])):
#             if copy_exp_list[i][j] in touch_keys_list:
#                 copy_exp_list[i][j] = 1
#             else:
#                 copy_exp_list[i][j] = 0
#     # print(copy_exp_list)
#     serial_manager.change_touch(copy_exp_list, touch_keys_list)


def convert(touch_data):
    copy_exp_list = copy.deepcopy(exp_list)
    touch_keys = set()
    for i in touch_data.values():
        colors = set(get_colors_in_area(i["x"], i["y"]))
        touch_keys.update(exp_image_dict[rgb_str] for rgb_str in colors if rgb_str in exp_image_dict)
    touch_keys_list = list(touch_keys)
    copy_exp_list = [[1 if item in touch_keys_list else 0 for item in sublist] for sublist in copy_exp_list]
    serial_manager.change_touch(copy_exp_list, touch_keys_list)


def get_real_resolution():
    hDC = win32gui.GetDC(0)
    w = win32print.GetDeviceCaps(hDC, win32con.DESKTOPHORZRES)
    h = win32print.GetDeviceCaps(hDC, win32con.DESKTOPVERTRES)
    return w, h


def get_screen_size():
    w = GetSystemMetrics(0)
    h = GetSystemMetrics(1)
    return w, h


def draw_rect_alpha(surface, color, rect):
    shape_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(shape_surf, color, shape_surf.get_rect())
    surface.blit(shape_surf, rect)


def getevent():
    # 存储多点触控数据的列表
    touch_data = {}

    pygame.init()
    icon = pygame.image.load(icon_path)
    pygame.display.set_icon(icon)
    screen_width, screen_height = MONITOR_SIZE
    screen = pygame.display.set_mode((screen_width, screen_height), pygame.SRCALPHA, display=0)
    pygame.display.set_caption("maimai-windows-touch-panel")

    fuchsia = (128, 128, 128)
    hwnd = pygame.display.get_wm_info()["window"]
    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                           win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED)
    win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*fuchsia), 38 if EMU_BTN else 1, win32con.LWA_ALPHA)
    # win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*fuchsia), 0, win32con.LWA_COLORKEY)
    # win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, screen_width, screen_height, 
    #                   win32con.SWP_NOACTIVATE | win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
    screen.fill(fuchsia)  # 使用透明背景

    if EMU_BTN: 
        background_image = pygame.image.load("image\\image_bg.png").convert_alpha()
        screen.blit(background_image, (0, 0))
        button_c = pygame.Rect(930, 1815, 150, 110)
        button_x = pygame.Rect(0, 1815, 150, 110)
    button_aime = pygame.Rect(55, 485, 188, 130)  # x, y, width, height
    button_start = pygame.Rect(950, 512, 67, 75)
    draw_rect_alpha(screen, (0, 0, 0, 0), button_aime)
    draw_rect_alpha(screen, (0, 0, 0, 0), button_start)
    pygame.display.update()

    clock = pygame.time.Clock()
    while True:
        # start_time = time.perf_counter()
        clock.tick(6000)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                break
            elif event.type == pygame.FINGERDOWN or event.type == pygame.FINGERUP or event.type == pygame.FINGERMOTION:
                touch_id = event.finger_id
                touch_x, touch_y = event.x * screen_width, event.y * screen_height
                clac_touch_x = 0
                clac_touch_y = 0
                if event.type == pygame.FINGERDOWN or event.type == pygame.FINGERMOTION:
                    if EMU_BTN: 
                        if button_c.collidepoint(touch_x, touch_y):
                            win32api.keybd_event(0x43, 0, 0, 0)
                            win32api.keybd_event(0x43, 0, win32con.KEYEVENTF_KEYUP, 0)
                        elif button_x.collidepoint(touch_x, touch_y):
                            win32api.keybd_event(0x58, 0, 0, 0)
                            win32api.keybd_event(0x58, 0, win32con.KEYEVENTF_KEYUP, 0)
                    if button_aime.collidepoint(touch_x, touch_y):
                        win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
                    elif button_start.collidepoint(touch_x, touch_y):
                        win32api.keybd_event(0x33, 0, 0, 0)
                        win32api.keybd_event(0x33, 0, win32con.KEYEVENTF_KEYUP, 0)
                    touch_data[str(touch_id)] = {}
                    if not REVERSE_MONITOR:
                        clac_touch_x = int(touch_x * x_scale)
                        clac_touch_y = int(touch_y * y_scale)
                    else:
                        clac_touch_x = int((MONITOR_SIZE[0] - touch_x) * x_scale)
                        clac_touch_y = int((MONITOR_SIZE[1] - touch_y) * y_scale)
                    touch_data[str(touch_id)]["x"] = clac_touch_x
                    touch_data[str(touch_id)]["y"] = clac_touch_y
                elif event.type == pygame.FINGERUP:
                    if button_aime.collidepoint(touch_x, touch_y):
                        win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
                    touch_data.pop(str(touch_id))
                convert(touch_data)
                if not DEBUG:
                    continue
                if event.type == pygame.FINGERDOWN:
                    print(f"Touch Down: ID={touch_id}, X={clac_touch_x}, Y={clac_touch_y}")
                elif event.type == pygame.FINGERUP:
                    print(f"Touch Up: ID={touch_id}, X={clac_touch_x}, Y={clac_touch_y}")
                elif event.type == pygame.FINGERMOTION:
                    print(f"Touch Motion: ID={touch_id}, X={clac_touch_x}, Y={clac_touch_y}")
        # print("单次执行时间:", (time.perf_counter() - start_time) * 1e3, "毫秒")


if __name__ == "__main__":
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    import pygame

    yaml_file_path = 'config.yaml'
    if len(sys.argv) > 1:
        yaml_file_path = sys.argv[1]
    if os.path.isfile(yaml_file_path):
        print("使用配置文件:", yaml_file_path)
        with open(yaml_file_path, 'r', encoding='utf-8') as file:
            c = yaml.safe_load(file)
        DEBUG = c["DEBUG"]
        EMU_BTN = c["EMU_BTN"]
        IMAGE_PATH = c["IMAGE_PATH"]
        COM_PORT = c["COM_PORT"]
        COM_BAUDRATE = c["COM_BAUDRATE"]
        AREA_SCOPE = c["AREA_SCOPE"]
        AREA_POINT_NUM = c["AREA_POINT_NUM"]
        REVERSE_MONITOR = c["REVERSE_MONITOR"]
        TOUCH_THREAD_SLEEP_MODE = c["TOUCH_THREAD_SLEEP_MODE"]
        TOUCH_THREAD_SLEEP_DELAY = c["TOUCH_THREAD_SLEEP_DELAY"]
        exp_image_dict = c["exp_image_dict"]
    else:
        print("未找到配置文件, 使用默认配置")

    MONITOR_SIZE = get_screen_size()
    exp_image = Image.open(IMAGE_PATH)
    exp_image_width, exp_image_height = exp_image.size
    x_scale = exp_image_width / MONITOR_SIZE[0]
    y_scale = exp_image_height / MONITOR_SIZE[1]
    print(f"定位图路径: {IMAGE_PATH}")
    print(f"定位图大小: [{exp_image_width}, {exp_image_height}]")
    print(f"触摸屏幕大小: {MONITOR_SIZE}")
    print(f"X轴缩放比例: {x_scale}")
    print(f"Y轴缩放比例: {y_scale}")
    print(('已' if REVERSE_MONITOR else '未') + "开启屏幕反转")
    serial_manager = SerialManager()
    serial_manager.start()
    threading.Thread(target=getevent).start()
    while True:
        input_str = input().strip()
        if len(input_str) == 0:
            continue
        if input_str == 'start':
            serial_manager.startUp = True
            print("已连接到游戏")
        elif input_str == 'reverse':
            REVERSE_MONITOR = not REVERSE_MONITOR
            print("已" + ('开启' if REVERSE_MONITOR else '关闭') + "屏幕反转")
        elif input_str == 'restart':
            restart_script()
        else:
            print("未知的输入")
