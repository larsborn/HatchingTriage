from setuptools import setup

setup(
   name='Hatching Triage Command-Line Client',
   version='1.0',
   description='A command-line client for the tria.ge API',
   author='Lars Wallenborn',
   author_email='lars@wallenborn.net',
   packages=['hatching-triage'],
   install_requires=['requests'],
)
