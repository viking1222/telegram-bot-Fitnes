import json
import os
from datetime import datetime

class Storage:
    def __init__(self, filename, default_data=None):
        self.filename = filename
        self.default_data = default_data if default_data is not None else {}
        self.data = self.load()

    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return self.default_data
        else:
            self.save(self.default_data)
            return self.default_data

    def save(self, data=None):
        if data is not None:
            self.data = data
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()
        return value

    def append_to_list(self, key, item):
        if key not in self.data or not isinstance(self.data[key], list):
            self.data[key] = []
        self.data[key].append(item)
        self.save()
        return self.data[key]
