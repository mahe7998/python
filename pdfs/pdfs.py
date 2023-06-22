#!/usr/bin/python3
# Author: Teshan Liyanage <teshanuka@gmail.com>
# To install PyPDF2, do `pip install PyPDF2`
import PyPDF2
import argparse
import os
import re

YELLOW = '\033[0;33m'
RED = '\033[0;31m'
ENDC = '\033[0m'

def colorize(txt, start, end, color=RED):
    return f"{txt[:start]}{color}{txt[start:end]}{ENDC}{txt[end:]}"

def search_in(file, pattern):
    with open(file, 'rb') as fp:
        reader = PyPDF2.PdfFileReader(fp)
        print(f"\n{YELLOW}>>> opening {file} ({reader.numPages} pages){ENDC}")
        for pn in range(reader.numPages):
            pg = reader.getPage(pn)
            txt = pg.extractText()
            for i, l in enumerate(txt.split('\n')):
                match = re.match(pattern, l)
                if match is not None:
                    print(f"{pn+1}:{i+1}: {colorize(l, *match.span())}")

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Folder of Files to search", type=str, nargs='+')
    parser.add_argument("pattern", help="String/pattern to search (regex)", type=str)    
    args = parser.parse_args()
    return args.path, args.pattern

if __name__ == '__main__':
    path, pattern = get_args()
    for root, dirs, files in os.walk("./RPM", topdown=False):
        for name in files:
            if name.endswith(".pdf"):
                print(os.path.join(root, name))
                search_in(os.path.join(root, name), pattern)

#            if file.endswith(".pdf"):
#                print(os.path. join(root, file))
#                search_in(file, pattern)
