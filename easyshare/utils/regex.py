import re

I_BEGIN_REGEX = re.compile(r"<([iI]\d+)>")
I_END_REGEX = re.compile(r"</([iI]\d+)>")
# I_REGEX = re.compile(r"<([/?iI]\d+)>")
I_REGEX = re.compile(r"^<([/?i]\d+)>")

if __name__ == "__main__":
    a = "<i3>a fancy str <i4> string"
    m = re.fullmatch(I_REGEX, a)
    print(m)

    a = "a fancy str <I7> string </i9>"
    m = re.findall(I_REGEX, a)
    print(m)

    a2 = re.sub(I_REGEX, "", a)
    print(a2)