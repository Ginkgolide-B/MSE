class DeleteItem:
    def __init__(self, iterable):
        self.iterable = list(iterable)

    def delete(self, element, DeleteIndex):
        length = len(self.iterable)
        for i in range (DeleteIndex, length, 1):
            self.iterable[i - 1] = self.iterable[i]
        self.iterable.pop(i)
        return self.iterable

a = [1,2,3,4,5,6,7,8,9]
print(DeleteItem(a).delete(a,5))