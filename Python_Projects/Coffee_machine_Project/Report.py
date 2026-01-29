#import regular expression
import re
#import time module for sleep
import time
#importing progress bar module
from tqdm import tqdm
#import Math module
from math import *
#importing coffeemachineprojectvariables file in order to use that file variable here
from coffeemachineprojectvariables import *
class coffee4:
    def report(self):
        if (dic['water'] == 0):
            print("\033[1;34mWater Is Empty Please Contact Employee to fill Water Using Employee OPtion in Machine\033[0m")
        if (dic['milk'] == 0):
            print("\033[1;34mMilk Is Empty Please Contact Employee to fill Milk Using Employee OPtion in Machine\033[0m")
        if (dic['sugar'] == 0):
            print("\033[1;34mSugar Is Empty Please Contact Employee to fill Sugar Using Employee OPtion in Machine\033[0m")
        if (dic['coffee'] == 0):
            print("\033[1;34mCoffee Is Empty Please Contact Employee to fill Coffee sing Employee OPtion in Machine\033[0m")
        if (dic['money'] == 0):
            print("\033[1;34mMoney Is Empty Please Contact Employee to fill Change Using Employee OPtion in Machine\033[0m")
        print("-" * 100)
        print("#" * 100)
        print("\033[1;31mMachine Report\033[0m")
        print("#" * 100)
        print("\033[1;32mRemaining_water:%.1fMl" % dic['water'])
        print("Milk in Machine:%.1fMl" % dic['milk'])
        print("Sugar in Machine:%.3fKg" % dic['sugar'])
        print("Coffee in Machine:%.3fKg" % dic['coffee'])
        print("Money:%.1f\033[0m" % dic['money'])