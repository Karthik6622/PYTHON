import sqlite3
connection=sqlite3.connect("info.db")
cursor=connection.cursor()
cursor.execute("create table student(name,age)")
print("Enter the 10 student names and their ages respectively:")
for i in range(10):
        who=[input("Enter name:")]
        age=int[input("Enter age:")]
        n=len(who)
        for i in range(n):
            cursor.execute("insert into student values(?,?)",(who[i],age[i]))
cursor.execute("select * From student order by age desc")
print("Displaying All the records from student Table  in descending order of age ")
print(*cursor.fetchall(),sep='/n')
