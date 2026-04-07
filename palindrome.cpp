#include <iostream>
using namespace std;
#include <vector>
class MyString {
vector<char> thestring;
vector<char>::iterator fi;
public:
bool Pal() {
int start = 0, end;
RemoveSpace();
UpCase();
end = thestring.size()-1;
while(start<=end)
if(thestring[start]==thestring[end]){
start++;
end--;
}
else
{
return false;
}
return true;
}
void RemoveSpace(){
for(fi = thestring.begin(); fi != 
thestring.end();++fi)
if(*fi == ' ')
thestring.erase(fi);
}
void UpCase() {
for(fi = thestring.begin(); fi != 
thestring.end();++fi)
if(*fi>='a' && *fi<='z')
*fi = *fi - 32;
}
void GetString(){
char c;
cout << "Enter a string:";
cin >> c;
while (c != '\n'){
thestring.push_back(c);
cin.get(c);
}
}
void WriteString() {
for(fi = thestring.begin(); fi != 
thestring.end();++fi)
cout << *fi;
}
};
int main () {
MyString s;
s.GetString();
if(s.Pal()) 
cout << "Palindrome";
else
cout << "Not a palindrome";
cout << endl;
return 0;
}
```

---

**Step 3: Compile it**

In Command Prompt:
```
cd C:\gcov_test
g++ -g -O0 -coverage palindrome.cpp
```
You should now see `a.exe`, `palindrome.gcno`, and `palindrome.gcda` in the folder.

---

**Step 4: Run 3 times to cover all lines**

**Run 1** (palindrome — hits the `true` path):
```
a.exe
```
Type `racecar` → press Enter → you should see `Palindrome`

Then immediately run:
```
gcov -c -m palindrome
```

**Run 2** (not a palindrome — hits `return false`):
```
a.exe
```
Type `hello` → press Enter → you should see `Not a palindrome`

Then run:
```
gcov -c -m palindrome
```

**Run 3** (palindrome with space — hits the `RemoveSpace` erase line):
```
a.exe
```
Type `race car` → press Enter → you should see `Palindrome`

Then run:
```
gcov -c -m palindrome