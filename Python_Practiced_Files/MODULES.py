
# MODULES

# In[4]:
list1=[688,8776,980]
def findchar(n):
        dic={}
        a='abcdefghijklmnopqrstuvwxyz'
        s=str(a)
        leng=len(s)
        for i in range(leng):
            dic.update({i+1:'{}'.format(s[i])})
        for i in str(n):
            print(dic[int(i)],end="")
        print()

def findnumber(n):
    b='abcdefghijklmnopqrstuvwxyz'
    dic1={}
    for e,i in enumerate(b):
        dic1.update({'{}'.format(i):e+1})
    for j in n:
        print(dic1[j],end="")
    print()
def lenofstring(n):
    s=0
    for i in n:
        s+=1
    print("The length of given string is:",s)
    
    