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
class coffee5:
    def employee(self):
        add_money = 0
        print("*" * 100)
        print("\033[1;32mRemaining Water in Machine:%.1fMl" % dic['water'])
        print("Remaining Milk in Machine:%.1fMl" % dic['milk'])
        print("Remaining Sugar in Machine:%.3fKg" % dic['sugar'])
        print("Remaining Coffee in Machine:%.3fKg" % dic['coffee'])
        print("Total Money:%.1f\033[0m" % dic['money'])
        print("*" * 100)
        refill = input("\033[1;35mWant to Refill(yes/no):\033[0m")
        if (re.search('^yes$|^YES$', refill, re.IGNORECASE)):
            try:
                passcode = int(input("\033[1;35mEnter your Employee passcode:\033[0m"))
                l = re.findall("\d", str(passcode))
                ll = "".join(l)
            except ValueError:
                print("Please Enter Only Numeric Numbers")
            else:
                if (passcode == 9999):
                    print("*" * 100)
                    print("\033[1;32mTotal Machine Water Capacity-10ml")
                    print("Total Machine Milk Capacity-10ml")
                    print("Total Machine Sugar Capacity-8Kg")
                    print("Total Machine Coffe Capacity-10ml-8Kg\033[0m")
                    print("*" * 100)
                    fillable_water = round(10 - round(dic['water'], 1), 1)
                    fillable_milk = round(10 - round(dic['milk'], 1), 1)
                    fillable_sugar = round(8 - round(dic['sugar'], 1), 1)
                    fillable_coffee = round(8 - round(dic['coffee'], 1), 1)
                    if (fillable_water != 0):
                        try:
                            additional_water = float(input(
                                "\033[1;35mEnter the water in ml and you can fill till %.1fML:\033[0m" % fillable_water))
                        except ValueError:
                            print("Please Enter Proper Integer or Float Value!!!You Entered Value is Incorrect")
                        else:
                            if (additional_water <= fillable_water):
                                dic['water'] = round(dic['water'] + additional_water, 1)
                                print("\033[1;34mWater has been added in the machine\033[0m")
                            else:
                                print("\033[1;31mYOU Entered Morethan Capacity of water\033[0m")
                    else:
                        print("\033[1;31mWater Is FULL! No need to fill the Water\033[0m")
                    if (fillable_milk != 0):
                        try:
                            additional_milk = float(input(
                                "\033[1;35mEnter the milk in ml and you can fill till  %.1fML:\033[0m" % fillable_milk))

                        except ValueError:
                            print("Please Enter Proper Integer or Float Value!!!You Entered Value is Incorrect")
                        else:
                            if (additional_milk <= fillable_milk):
                                dic['milk'] = round(dic['milk'] + additional_milk, 1)

                                print("\033[1;34mMilk has been added in the machine\033[0m")
                            else:
                                print("\033[1;32mYOU Entered Morethan Capacity of milk\033[0m")
                    else:
                        print("\033[1;32mMilk Is FULL! No need to fill the Milk\033[0m")
                    if (fillable_sugar != 0):
                        try:
                            additional_sugar = float(input(
                                f"\033[1;35mEnter the sugar in kg and you can fill till  %.1fKG\033[0m:" % fillable_sugar))
                        except ValueError:
                            print("Please Enter Proper Integer or Float Value!!!You Entered Value is Incorrect")
                        else:
                            if (additional_sugar <= fillable_sugar):
                                dic['sugar'] = round(dic['sugar'] + additional_sugar, 1)
                                print("\033[1;34mSugar has been added in the machine\033[0m")
                            else:
                                print("\033[1;31mYOU Entered Morethan Capacity of sugar\033[0m")
                    else:
                        print("\033[1;31mSugar Is FULL! No need to fill the Sugar\033[0m")
                    if (fillable_coffee != 0):
                        try:
                            additional_coffee = float(
                                input("Enter the coffee in kg and you can fill till %.1fKg:" % fillable_coffee))
                        except ValueError:
                            print("Please Enter Proper Integer or Float Value!!!You Entered Value is Incorrect")
                        else:
                            if (additional_coffee <= fillable_coffee):
                                dic['coffee'] = round(dic['coffee'] + additional_coffee, 1)
                                print("Coffee has been added in the machine")
                            else:
                                print("YOU Entered Morethan Capacity of Coffee")
                    else:
                        print("Water Is FULL! No need to fill the Water")
                    inp_money_yes = input("Do you want do add any money(yes/no)")
                    if (re.search('^yes$|^YES$', inp_money_yes, re.IGNORECASE)):
                        try:
                            add_money = float(input("Enter money below 100:"))
                        except (ValueError, UnboundLocalError):
                            print("Please Enter Integer Number Below 100 but You Entered Wrong!!!")
                        else:
                            if (add_money < 100):
                                dic['money'] = round(dic['money'] + add_money, 1)
                                print("Money has been added")
                            else:
                                print("Please add lessthan 100 rupees")
                    elif (re.search('^no$|^NO$', inp_money_yes, re.IGNORECASE)):
                        print("Check The Report and please keep meachine with proper change Cause you Selected No")
                    else:
                        print("You Have been Selected OtherThan Yes or No So Money Won't be Add to machine")

                elif (not (re.search("^....$", ll))):
                    print("Please Enter Proper 4digit Numeric Passcode")
                else:
                    print("Please Enter proper Employee passcode")
        elif (re.search('^no$|^NO$', refill, re.IGNORECASE)):
            print("You Selected No...check the meachine status and fill it!!!")
        else:
            print("You Have been Selected OtherThan Yes or No So Resource Won't be Add to machine")