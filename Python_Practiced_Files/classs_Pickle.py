class emp():
    def __init__(self,id,name,native):
        self.id=id
        self.name=name
        self.native=native
    def display(self):
        print(f"Emp id is: {self.id} and Emp name is: {self.name} and Employee native from: {self.native}")