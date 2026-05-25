from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
import sys
import time
import wave


# 프로그램이 있는 폴더를 기준으로 녹음 파일 저장 위치를 정함
APP_DIR = Path(__file__).resolve().parent
RECORDS_DIR = APP_DIR / 'records'
FILE_EXTENSION = '.wav'
FILE_NAME_FORMAT = '%Y%m%d-%H%M%S'

# 기본 녹음 설정입니다.
DEFAULT_DURATION = 5
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_CHANNELS = 1
DEFAULT_SAMPLE_WIDTH = 2


def load_sounddevice():
    # sounddevice가 없으면 현재 Python 실행 파일 기준 설치 명령을 안내
    try:
        import sounddevice
    except ImportError:
        print('The recording feature requires the sounddevice package.')
        print(f'Install it with: & "{sys.executable}" -m pip install sounddevice')
        return None

    return sounddevice


def ensure_records_dir():
    # records 폴더가 없으면 새로 만듦
    RECORDS_DIR.mkdir(exist_ok=True)


def make_record_path(recorded_at=None):
    # 녹음 시각을 파일명으로 사용해 파일명이 겹치지 않게 함
    if recorded_at is None:
        recorded_at = datetime.now()

    file_name = recorded_at.strftime(FILE_NAME_FORMAT) + FILE_EXTENSION
    return RECORDS_DIR / file_name


def parse_positive_int(value, default_value):
    # 비어 있거나 잘못된 값이면 기본값을 사용함
    value = value.strip()

    if not value:
        return default_value

    try:
        number = int(value)
    except ValueError:
        return default_value

    if number <= 0:
        return default_value

    return number


def parse_optional_int(value):
    # 마이크 번호를 입력하지 않으면 기본 장치를 사용하도록 None을 반환
    value = value.strip()

    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def get_input_devices(sounddevice):
    # 입력 채널이 있는 장치만 마이크 목록에 포함
    devices = sounddevice.query_devices()
    input_devices = []

    for index, device in enumerate(devices):
        channels = int(device.get('max_input_channels', 0))

        if channels > 0:
            input_devices.append((index, device))

    return input_devices


def show_microphones():
    # 사용 가능한 마이크 목록을 화면에 보여줌
    sounddevice = load_sounddevice()

    if sounddevice is None:
        return []

    input_devices = get_input_devices(sounddevice)

    if not input_devices:
        print('No input microphone was found.')
        return []

    print('Available microphones:')

    for index, device in input_devices:
        name = device.get('name', 'Unknown')
        channels = int(device.get('max_input_channels', 0))
        sample_rate = int(device.get('default_samplerate', 0))
        print(f'{index}: {name} ({channels} channels, {sample_rate} Hz)')

    return input_devices


def record_audio(duration, device_index=None):
    # 지정한 시간 동안 마이크 입력을 wav 파일로 저장
    sounddevice = load_sounddevice()

    if sounddevice is None:
        return None

    ensure_records_dir()
    record_path = make_record_path()
    audio_queue = Queue()

    def audio_callback(indata, frames, time_info, status):
        # 오디오 콜백은 짧게 끝나야 하므로 큐에 넣고 실제 저장은 바깥에서 처리
        del frames, time_info, status
        audio_queue.put(bytes(indata))

    try:
        with wave.open(str(record_path), 'wb') as wav_file:
            # wav 파일 헤더에 저장할 오디오 형식을 설정
            wav_file.setnchannels(DEFAULT_CHANNELS)
            wav_file.setsampwidth(DEFAULT_SAMPLE_WIDTH)
            wav_file.setframerate(DEFAULT_SAMPLE_RATE)

            with sounddevice.RawInputStream(
                samplerate=DEFAULT_SAMPLE_RATE,
                blocksize=0,
                device=device_index,
                channels=DEFAULT_CHANNELS,
                dtype='int16',
                callback=audio_callback,
            ):
                print(f'Recording for {duration} seconds...')
                end_time = time.monotonic() + duration

                # 녹음이 끝날 때까지 큐에 쌓인 오디오 데이터를 파일에 기록
                while time.monotonic() < end_time:
                    try:
                        wav_file.writeframes(audio_queue.get(timeout=0.2))
                    except Empty:
                        continue

                # 녹음 종료 직후 큐에 남아 있는 마지막 데이터를 마저 저장
                while not audio_queue.empty():
                    wav_file.writeframes(audio_queue.get())

    except sounddevice.PortAudioError as error:
        print(f'Recording failed: {error}')
        return None

    print(f'Saved: {record_path}')
    return record_path


def parse_date(value, is_end=False):
    # YYYYMMDD와 YYYY-MM-DD 두 가지 날짜 입력 형식을 지원
    value = value.strip()

    for date_format in ('%Y%m%d', '%Y-%m-%d'):
        try:
            parsed_date = datetime.strptime(value, date_format)
        except ValueError:
            continue

        if is_end:
            # 종료일은 해당 날짜의 마지막 시각까지 포함
            return parsed_date.replace(hour=23, minute=59, second=59)

        return parsed_date

    return None


def get_recorded_at(file_path):
    # 파일명에서 녹음 시각을 다시 읽어옴
    try:
        return datetime.strptime(file_path.stem, FILE_NAME_FORMAT)
    except ValueError:
        return None


def find_records_between(start_date, end_date):
    # records 폴더에서 날짜 범위에 들어오는 녹음 파일만 찾음
    ensure_records_dir()
    records = []

    for file_path in RECORDS_DIR.glob(f'*{FILE_EXTENSION}'):
        recorded_at = get_recorded_at(file_path)

        if recorded_at is None:
            continue

        if start_date <= recorded_at <= end_date:
            records.append((recorded_at, file_path))

    return sorted(records)


def show_records_between():
    # 사용자가 입력한 시작일과 종료일 사이의 녹음 파일을 출력
    start_value = input('Start date (YYYYMMDD or YYYY-MM-DD): ')
    end_value = input('End date (YYYYMMDD or YYYY-MM-DD): ')

    start_date = parse_date(start_value)
    end_date = parse_date(end_value, is_end=True)

    if start_date is None or end_date is None:
        print('Invalid date format.')
        return

    if start_date > end_date:
        print('Start date must be earlier than end date.')
        return

    records = find_records_between(start_date, end_date)

    if not records:
        print('No recordings were found in that date range.')
        return

    print('Recordings:')

    for recorded_at, file_path in records:
        recorded_time = recorded_at.strftime('%Y-%m-%d %H:%M:%S')
        print(f'{recorded_time} - {file_path.name}')


def prompt_recording():
    # 녹음 전 마이크 목록을 보여주고, 녹음 시간과 장치 번호를 입력받음
    show_microphones()
    duration_value = input(f'Duration in seconds [{DEFAULT_DURATION}]: ')
    device_value = input('Microphone number [default]: ')
    duration = parse_positive_int(duration_value, DEFAULT_DURATION)
    device_index = parse_optional_int(device_value)
    record_audio(duration, device_index)


def show_menu():
    # 메인 메뉴를 출력
    print()
    print('Javis voice recorder')
    print('1. Show microphones')
    print('2. Record voice')
    print('3. Show recordings by date range')
    print('4. Exit')


def run():
    # 사용자가 종료를 선택할 때까지 메뉴를 반복
    while True:
        show_menu()
        choice = input('Select menu: ').strip()

        if choice == '1':
            show_microphones()
        elif choice == '2':
            prompt_recording()
        elif choice == '3':
            show_records_between()
        elif choice == '4':
            print('Goodbye.')
            break
        else:
            print('Please select 1, 2, 3, or 4.')


if __name__ == '__main__':
    try:
        run()
    except KeyboardInterrupt:
        print()
        print('Program stopped.')
        sys.exit(0)
