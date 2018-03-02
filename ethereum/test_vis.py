import pytest
from ethereum.tools import tester
from ethereum.tests.utils import new_db
from ethereum.db import EphemDB
from ethereum.hybrid_casper import casper_utils
from ethereum.slogging import get_logger
from ethereum.tests.hybrid_casper.testing_lang import TestLangHybrid
from ethereum.visualization import CasperVisualization

log = get_logger('test.chain')
logger = get_logger()

_db = new_db()

@pytest.fixture(scope='function')
def db():
    return EphemDB()
alt_db = db


test_string = 'B J0 J1 J2 J3 J4 B B B S0 B V0 V1 V2 B V0 V1 V2 V3 V4 B S1 R0 B B B B B B B B V0 V1 V2 B1 H1'
test = TestLangHybrid(5, 100, 0.02, 0.002)
test.parse(test_string)

cv = CasperVisualization('epoch', test.t, True)
 
cv.draw()
