from setuptools import setup

setup(
    name = 'votecounter',
     version = '0.1-alpha',    

    description = 'Vote counter for several contest models',
    url = 'https://github.com/flimao/votecounter',
    author = 'Felipe Oliveira',
    author_email = 'votecounter@dev.lmnice.me',
    long_description = open('README.md').read(),
    license = 'LICENSE',
    packages = ['votecounter', 'votecounter.test' ],
    install_requires = [
        'numpy', 'pandas', 'requests', 'pathlib', 'wget', 'asn1tools', 'ratelimiter', 'tqdm'
    ],

    classifiers = [
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Financial and Insurance Industry',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',        
        'Programming Language :: Python :: 3 :: Only',
    ],
)
