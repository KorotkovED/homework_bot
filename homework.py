import telegram
import requests
import os
import logging
from dotenv import load_dotenv
import time
import json

load_dotenv()


PRACTICUM_TOKEN = os.getenv('practicum_token')
TELEGRAM_TOKEN = os.getenv('telegram_token')
TELEGRAM_CHAT_ID = os.getenv('telegram_chat_id')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    filename='program.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)
logger.addHandler(
    logging.StreamHandler()
)


class NotDocumentStatusError(Exception):
    """
    Ошибка не объявленного статуса д/з.
    Возникает, когда полученный статус не равен тем,
    которые есть в 'HOMEWORK_VERDICTS'.
    """

    pass


class UrlApiError(Exception):
    """
    Ошибка подключения к ENDPOINT.
    Возникает, когда код поключения не равен 200.
    """

    pass


class RequestExceptionError(Exception):
    """Ошибка запроса."""

    pass


class EmptyDictionaryOrListError(Exception):
    """Ошибка пустой структуры."""

    pass


def check_tokens():
    """
    Проверяет доступность переменных окружения.
    которые необходимы для работы программы.
    """
    token_error = False
    tokens_msg = (
        'Программа принудительно остановлена. '
        'Отсутствует обязательная переменная окружения:')
    if PRACTICUM_TOKEN is None:
        token_error = True
        logger.critical(f'{tokens_msg} PRACTICUM_TOKEN')
    elif TELEGRAM_TOKEN is None:
        token_error = True
        logger.critical(f'{tokens_msg} TELEGRAM_TOKEN')
    elif TELEGRAM_CHAT_ID is None:
        token_error = True
        logger.critical(f'{tokens_msg} TELEGRAM_CHAT_ID')
    return token_error


def send_message(bot, message):
    """
    Отправляет сообщение в Telegram чат.
    На входе: инициализоваронный бот и сообщение о статусе д/з.
    """
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение успешно отправлено!')
    except telegram.TelegramError as tel_error:
        logger.error(f'Отправка сообщения прервана ошибкой {tel_error}!')


def get_api_answer(timestamp):
    """
    Делает запрос энпоинту API-сервиса.
    На входе: дата от которой нужно смотреть статус д/з,
    На выходе: все данные о д/з.
    """
    PAYLOAD = {'from_date': timestamp}
    try:
        response = requests.get(url=ENDPOINT, headers=HEADERS, params=PAYLOAD)
        if response.status_code != 200:
            api_msg = (
                f'Эндпоинт {ENDPOINT} недоступен.'
                f' Код ответа API: {response.status_code}')
            logger.error(f'{api_msg}')
            raise UrlApiError(f'{api_msg}')
        return response.json()

    except requests.exceptions.RequestException as request_error:
        text_error = f'Код ответа API (RequestException): {request_error}'
        logger.error(text_error)
        raise RequestExceptionError(text_error) from request_error

    except json.JSONDecodeError as value_error:
        text_error = f'Код ответа API (ValueError): {value_error}'
        logger.error(text_error)
        raise json.JSONDecodeError(text_error) from value_error


def check_response(response):
    """
    Проверяет ответ API на соответствие документации.
    На входе: запрос к сервису,
    На выходе: конкретное д/з.
    """
    if type(response) != dict:
        text_error = 'Структура данных не соответсвует словарю!'
        logger.error(text_error)
        raise TypeError(text_error)

    if response.get('homeworks') is None:
        text_error = ('Ошибка ключа homeworks или response'
                      'имеет неправильное значение.')
        logger.error(text_error)
        raise EmptyDictionaryOrListError(text_error)

    if type(response.get('homeworks')) != list:
        text_error = 'Структура данных не соответсвует списку!'
        logger.error(text_error)
        raise TypeError(text_error)
    return response['homeworks'][0]


def parse_status(homework):
    """
    Извлекает из информации о конкретной домашней работе.
    статус этой работы.
    На входе: переменная 'homework' (конкретное д/з)
    На выходе: строка сообщения с параметрами 'homework_name'(название д/з),
            'verdict'(статус д/з).
    """
    status = homework.get('status')
    homework_name = homework.get('homework_name')

    if status not in HOMEWORK_VERDICTS:
        text_error = 'Недокументированный формат статуса!'
        logger.error(text_error)
        raise NotDocumentStatusError(text_error)

    if homework_name is None:
        logger.error(
            'Ошибка пустое значение homework_name: ', homework_name)
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    tokens_error = check_tokens()
    if tokens_error is True:
        message = 'Кажется что-то пошло не так :((('
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(message)
        exit()

    timestamp = int(time.time())
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text='Я начал отслеживание!')
    hw_status = 'reviewing'
    errors = True

    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            if homework and hw_status != homework['status']:
                message = parse_status(homework)
                send_message(bot, message)
                hw_status = homework['status']
                logger.info(f'Обновление статуса домашки на {hw_status}')
            else:
                logger.info('Изменений нет!')
            time.sleep(RETRY_PERIOD)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if errors:
                errors = False
                send_message(bot, message)
                logger.debug(message)
            logging.critical(message)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
