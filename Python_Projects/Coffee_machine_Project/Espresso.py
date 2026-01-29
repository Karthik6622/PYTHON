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
class coffee3:
    def espresso(self):
        # if milk is not empty then it will go inside the if statement
        if (dic['milk'] != 0):
            # if water is not empty then it will go inside the if statement
            if (dic['water'] != 0):
                # if sugar is not empty then it will go inside the if statement
                if (dic['sugar'] != 0):
                    # if Coffee is not empty then it will go inside the if statement
                    if (dic['coffee'] != 0):
                        # here Explaning one capacino rate
                        print("-" * 100)
                        print("\033[1;34m1 Espresso rate is 20Rupees\033[0m")
                        print("-" * 100)
                        # one expresso need 100ml water,200ml milk and 25g sugar and 25g coffee
                        # here getting how much expresso user want
                        try:
                            count_espresso = int(input("\033[1;35mSelect no of Expresso do you want?:\033[0m"))
                        except:
                            print("Please Enter Numerical Value")
                        else:
                            # checkcing if machine water level equal or morethan making expresso for user need or not
                            # count_espresso*0.100=total water need for customer request
                            if (dic['water'] >= count_espresso * 0.100):
                                # checkcing if machine milk level equal or morethan making capacino for user need or not
                                # count_espresso*0.200=total milk need for customer request
                                if (dic['milk'] >= count_espresso * 0.200):
                                    # checkcing if machine sugar level equal or morethan making capacino for user need or not
                                    # count_espresso*0.025=total sugar need for customer request
                                    if (dic['sugar'] >= (count_espresso * 0.025)):
                                        # checkcing if machine Coffee Powder level equal or morethan making capacino for user need or not
                                        # count_espresso*0.025=total coffee need for customer request
                                        if (dic['coffee'] >= (count_espresso * 0.025)):
                                            # here displaying capacino total rate
                                            print(
                                                f'\033[1;34mYou Have Selected {count_espresso} Espresso Rate is:{count_espresso * 20}\033[0m')
                                            # getting money from user for capacino
                                            try:
                                                espresso_money = float(input(
                                                    "\033[1;35mPlease Pay Money For Your Espresso As Mentoned Above:\033[0m"))
                                            except:
                                                print("Please Enter Numerical Or Decimal Value")
                                            else:
                                                # checking user paying money is morethan payable money if it is equal or more it will go inside
                                                if (espresso_money >= count_espresso * 20):
                                                    # dic['money']=machine money
                                                    # here checking we have enough money to give user as a change after user paid morethan actul money
                                                    if (dic['money'] >= espresso_money - count_espresso * 20):
                                                        # subtracting water from the machine water
                                                        # subtracting milk from the machine milk
                                                        # subtracting Coffee from the machine sugar
                                                        # adding money into the machine money
                                                        dic['water'] = round(dic['water'] - 0.100 * count_espresso, 3)
                                                        dic['milk'] = round(dic['milk'] - 0.200 * count_espresso, 3)
                                                        dic['coffee'] = round(dic['coffee'] - 0.025 * count_espresso, 3)
                                                        dic['money'] = round(dic['money'] + espresso_money, 1)
                                                        print(
                                                            "\033[1;34mYour Order has been placed!!!please keep Cup near machine..\033[0m")
                                                        # here Filling espresso to user's cup one by one using while loop
                                                        j = 1
                                                        else_part = 0
                                                        while (j <= count_espresso):
                                                            temp_sugar = 0.0
                                                            # User selecting Sugar level
                                                            press_sugar = input(
                                                                "\033[1;35m\033[1;35mPlease Select sugar level For Your Capacino(High/Medium/Low):\033[0m")
                                                            # if user selected high,we will add sugar 0.025g to user espresso
                                                            if (re.search('^high$|^HIGH$', press_sugar, re.IGNORECASE)):
                                                                temp_sugar = round(temp_sugar + 0.025, 3)
                                                            # if user selected Medium,we will add sugar 0.020g to user espresso
                                                            elif (
                                                            (re.search('^medium$|^MEDIUM$', press_sugar, re.IGNORECASE))):
                                                                temp_sugar = round(temp_sugar + 0.020, 3)
                                                            # if user selected Low,we will add sugar 0.015g to user espresso
                                                            elif ((re.search('^low$|^LOW$', press_sugar, re.IGNORECASE))):
                                                                temp_sugar = round(temp_sugar + 0.015, 3)
                                                            else:
                                                                # if user has not selected any sugar levels,we defaultly providing medium sugar level to user espresso
                                                                print(
                                                                    "\033[1;31mYou Not Selected Proper Sugar Level so Machine provide defaulty Medium Sugar level!!!\033[0m")
                                                                temp_sugar = round(temp_sugar + 0.020, 3)
                                                                # This one Last confimation from the user to fill espresso

                                                            press_ok = input(
                                                                "\033[1;35mEnter Ok To Fill Espresso To Your Cup(If You Want to cancel your order please click cancel or other tahn ok):\033[0m")
                                                            print('*' * 100)

                                                            # once we get confirmation from user,we going to fill Espresso
                                                            if (re.search('^ok$|^OK$', press_ok, re.IGNORECASE)):
                                                                # here we subtracting sugar that how much used for espresso
                                                                dic['sugar'] = round(dic['sugar'] - temp_sugar, 3)
                                                                # Showing filling process by progress bar
                                                                for i in tqdm(range(10), desc="Espresso Is Filling",
                                                                              bar_format="\033[1;32m{l_bar}{bar}"):
                                                                    time.sleep(.2)
                                                                # once we given to user entered no of espresso, we displaying order completed Message
                                                                if (j == count_espresso):
                                                                    print(
                                                                        "\033[1;31mYour Order has been completed!!!Thankyou For Using Machine\033[1;35m")
                                                                # once we not given to user entered no of espresso, we asking to keep next cup
                                                                else:
                                                                    print(
                                                                        f"\033[1;31mFilled Up!!! Please Keep Next Cup ...Still {count_espresso - j} Cups Are Pending To Fill \033[0m")
                                                                j += 1

                                                            # unfortunitly if user clicked other than Ok,we calculating in Which Cup filling time user stopped and that stuffs adding again to machine

                                                            else:
                                                                else_part = 1
                                                                dic['water'] = round(
                                                                    dic['water'] + (0.100 * (count_espresso - j + 1)), 3)
                                                                dic['milk'] = round(
                                                                    dic['milk'] + (0.200 * (count_espresso - j + 1)), 3)
                                                                dic['coffee'] = round(
                                                                    dic['coffee'] + (0.025 * (count_espresso - j + 1)), 3)
                                                                # 20*count_espresso-j*20+20(j=2,count_espresso=5)
                                                                # 20*5-2*20+20
                                                                # 100-40+20
                                                                # 60+20
                                                                # 80
                                                                print(
                                                                    f"\033[1;3mYOU CLICKED OTHER THAN OK!!So Your Money {20 * count_espresso - j * 20 + 20}Rupees be there to give\033[0m")
                                                                print(
                                                                    f"Cause You ordered {count_espresso} Capacino but you cancelled before {count_espresso - j + 1} cup filling so we providig that money")
                                                                dic['money'] = round(
                                                                    dic['money'] - (20 * count_espresso - j * 20 + 20), 1)
                                                                if (espresso_money >= count_espresso * 20):
                                                                    change = 0
                                                                    change = round(espresso_money - count_espresso * 20 + (
                                                                                20 * count_espresso - j * 20 + 20), 1)
                                                                    print("\033[1;31myour Change Is:",
                                                                          round(espresso_money - count_espresso * 20, 1),
                                                                          "Rupees\033[0m")
                                                                    # after given change subtracting money from machine money
                                                                    dic['money'] = round(dic['money'] - (
                                                                                espresso_money - count_espresso * 20), 1)
                                                                print("Plese Collect Your Total Amount:", change)
                                                                j = count_espresso + 1

                                                        # here we calculating how much we must give change to user
                                                        if (espresso_money > count_espresso * 20 and else_part != 1):
                                                            print("\033[1;31mPlease collect your Change:",
                                                                  round(espresso_money - count_espresso * 20, 1),
                                                                  "Rupees\033[0m")
                                                            # after given change subtracting money from machine money
                                                            dic['money'] = round(
                                                                dic['money'] - (espresso_money - count_espresso * 20), 1)
                                                    else:
                                                        # if there is no change in the machine,we displaying below massage
                                                        print(
                                                            "\033[1;31mThere is not enough change in the machine so please enter below or equal to",
                                                            20 * count_espresso + dic['money'])
                                                else:
                                                    # if user enter less than actual money, we giving below msg and display how much less he paid from actual
                                                    remaining_money = count_espresso * 20 - espresso_money
                                                    print(
                                                        f"\033[1;31mPlease Pay enough money to purchase and you entering {remaining_money} Rupees lessthan from amount\033[0m")
                                        else:
                                            # here if there is not enough Coffee in the machine,we display msg and coffee enough for how much cups
                                            print("\033[1;31mSorry there is not enough Coffee")
                                            available_coffee = round(dic['coffee'] / 0.025)
                                            print(f"Coffee is available only for {available_coffee} Cup of Espresso")

                                    else:
                                        # here if there is not enough Sugar in the machine,we display msg and sugar enough for how much cups
                                        print("\033[1;31mSorry there is not enough Sugar")
                                        available_sugar = round(dic['sugar'] / 0.025)
                                        print(f"\033[1;31mSugar is available only for {available_sugar} Cup of Espresso")
                                else:
                                    # here if there is not enough Milk in the machine,we display msg and Milk enough for how much cups
                                    print("Sorry there is not enough milk")
                                    available_milk = round(dic['milk'] / 0.200)
                                    print(f"Milk is available only for {available_milk} Cup of Espresso")
                            else:
                                # here if there is not enough Water in the machine,we display msg and Water enough for how much cups
                                print("Sorry there is not enough water")
                                available_water = round(dic['water'] / 0.100)
                                print(f"Water is available only for {available_water} Cup of Espresso")
                    else:
                        # if Coffee is empty in machine,we telling to contact employee
                        print("Coffee is empty please contact employee")
                else:
                    # if sugar is empty in machine,we telling to contact employee
                    print("Sugar is empty please contact employee")
            else:
                # if su is empty in machine,we telling to contact employee
                print("Water is empty please contact employee")
        else:
            # if Milk is empty in machine,we telling to contact employee
            print("Milk is empty please contact employee\033[0m")