import json
import datetime
import decimal


def query_to_dict(result):
    result_dict = {}
    num = 1
    for row in result:
        row_dict = row._asdict()
        result_dict[f'row {num}'] = row_dict
        num += 1
    return result_dict


class QueryEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, datetime.datetime) or isinstance(obj, datetime.date):
            return obj.isoformat()
        elif isinstance(obj, decimal.Decimal):
            return float(obj)
        return json.JSONEncoder.default(self, obj)