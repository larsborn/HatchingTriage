# Hatching Triage API Client
Python-based Client for the [tria.ge] site.

## Installation

Requires at least Python 3.7 and the package `requests` to be installed. Fully compatible with being run in a virtual
environment. It is recommended to set the environment variable `HATCHING_TRIAGE_ACCESS_KEY` accordingly.

## Example Usage
After aliasing the script `hatching-triage.py` to `hatching` and setting the above-mentioned environment variable a 
session to download a sample base on a ID or to scrape the last 10 samples from the public feed:

```Batch
# URL to get the ID from: https://tria.ge/reports/200409-vmw4mgq77e/static1
$ hatching --debug download 200409-vmw4mgq77e
[DEBUG] Using User-Agent string: HatchingTriageClient/1.0.0 (python-requests 2.23.0) Windows (10)
[INFO] Writing 73728 bytes to "5a21120c9bd779786888f9d4d2a138836e627f001dbacc80c2b035ff7d198715"...

$ hatching --debug scrape .
[DEBUG] Using User-Agent string: HatchingTriageClient/1.0.0 (python-requests 2.23.0) Windows (10)
[DEBUG] Writing 49152 bytes to ".\samples\bb7136b4c21f0aeed644a4989605afb22fafd457fab5ad79f122a990bdc4beca"...
[DEBUG] Writing 25458624 bytes to ".\samples\e1a2f6046472d7712259d400b4a0f983f4ab986116a7804a9bc5adc1d663ba3b"...
[DEBUG] Writing 227328 bytes to ".\samples\5edd4cfef836b5c2d2c6434a8ddba223e606542a0e23c2764957c081496cbcd2"...
[DEBUG] Writing 199168 bytes to ".\samples\199f1e92827bbe3acf64d5a3b9d412133e30edafd804378ec55e556649809d88"...
[DEBUG] Writing 199168 bytes to ".\samples\a94e0688aadb1c8ee8309d87abd57b2b6ef1b820e4387e778ccf5e7c77c10d61"...
[DEBUG] Writing 342016 bytes to ".\samples\c2c89da1518a4950cedec3129aa86fce21ccec502586e44a7f3b3757b44a1e1c"...
[DEBUG] Writing 647680 bytes to ".\samples\0ea5d6d7d7e520a61a396c77d166dd1cb34cde965d3788430c3484a616381c74"...
[DEBUG] Writing 227328 bytes to ".\samples\5ccd4e872eea8765ef7429bfb97cda36530c505e5ce2fc32e37349c62924624e"...
[DEBUG] Writing 990967 bytes to ".\samples\b4efb9c7ace70554dd75469169533688c501e98ef565bc2a81d70881801effb4"...
[DEBUG] Writing 215887 bytes to ".\samples\dd1ee0b0756258f8b1aee5b2ce52395c1e8f5187ed11a27b7079c9d58519edf3"...
[DEBUG] 10 new sample(s) found.

$ hatching --debug scrape .
[DEBUG] Using User-Agent string: HatchingTriageClient/1.0.0 (python-requests 2.23.0) Windows (10)
[DEBUG] 0 new sample(s) found.
```

[tria.ge]: https://tria.ge/
