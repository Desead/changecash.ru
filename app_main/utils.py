class OrderName:
    '''
    Создаём новый номер ордера.
    '''
    len_name_default: int = 8  # длинна номера заявки по умолчанию

    @staticmethod
    def create_order_name(len_name: int = len_name_default):
        from string import ascii_uppercase, digits
        from random import choice

        temp: str = ''
        for i in range(len_name):
            if len(temp) % 5 == 4: temp += '_'
            temp += choice(ascii_uppercase + digits)

        return temp

