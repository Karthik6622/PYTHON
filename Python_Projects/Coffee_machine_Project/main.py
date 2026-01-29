from Capacino import *
from Latte import *
from Espresso import *
from Report import *
from Employee import *
c=coffee()
c1=coffee2()
c2=coffee3()
c3=coffee4()
c4=coffee5()
i=True
while i==True:
    print('='*100)
    print("\033[1;31m1.Capacino")
    print("2.Latte")
    print("3.Espresso")
    print("4.Report")
    print("5.Employee(To Fill Resource)")
    print("6.OFF\033[0m")
    print('='*100)
    choose=input("\033[1;35mPlease select one:\033[0m")
    if(re.search('^1$',choose)):
        c.capacino()
    elif(re.search('^2$',choose)):
        c1.latte()
    elif(re.search('^3$',choose)):
        c2.espresso()
    elif(re.search('^4$',choose)):
        c3.report()
    elif(re.search('^5$',choose)):
        c4.employee()
    elif(re.search('^6$',choose)):
        for j in tqdm(range(10),desc="\033[1;34mPowering Off",bar_format="{l_bar}{bar}\033[0m"):
            time.sleep(.5)
        print("\033[1;31mMeachine has been off\033[0m")
        i=False
    else:
        print("Please enter above mention one!!!")
        i=False