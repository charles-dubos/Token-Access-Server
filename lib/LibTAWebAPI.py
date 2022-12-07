#!/usr/bin/env python3
#- *- coding:utf-8 -*-
"""This module contains functions for Token Access Web API

The API simulates a management canal to :
- Request a HOTP token to send a message to a recipient managed by this system
- (Re-)generate a HOTP seed
"""
__author__='Charles Dubos'
__license__='GNUv3'
__credits__='Charles Dubos'
__version__="0.1.0"
__maintainer__='Charles Dubos'
__email__='charles.dubos@telecom-paris.fr'
__status__='Development'


# Built-in
from logging import getLogger


# Other libs
from fastapi import FastAPI, HTTPException, Form


# Owned libs
from lib.LibTAServer import *
from lib.LibTACrypto import getHotp, PreSharedKey
import lib.LibTADatabase as dbManage
from lib.LibTAPolicy import policy


# Module directives
## Load logger
logger=getLogger('tknAcsAPI')


## Loading database
logger.debug('Opening {} database:'.format( context.DATABASE['db_type'] ))
if context.DATABASE['db_type'] in ["sqlite3", "mysql"]:
    database = getattr(
        dbManage,
        context.DATABASE['db_type'] + "DB"
    )(**context.DATABASE)
else:
    raise FileNotFoundError


## Definition of API
app = FastAPI()


# API functions

## Global-level API points (all-public accessibles)
@app.get("/")
async def root():
    """Only returns a welcoming message.
    Used for connection-testing sake.
    """
    return {"message": "Welcome to Token access: a HOTP email validator.",
        "help":"See '/docs' for API documentation"
    }


@app.get("/requestToken/")
async def requestToken(sender: str, recipient: str):
    """Requests a HOTP token for external sender to recipient (user).

    Args:
        sender (str): email address of sender
        recipient (str): email adress of recipient

    Raises:
        ValueError (HTTP/418): Bad email address
        PermissionError (HTTP/406): Recorded inner policy not allowing this connection 

    Returns:
        json: formatted with {"token","allowed_for": {"from", "to"}}
    """
    try:
        recipientAddr = EmailAddress().parser(recipient)
        if not database.isInDatabase(userEmail=recipientAddr.getEmailAddr()):
            raise PermissionError

        if not policy(sender, recipient):
            raise PermissionError

        preSharedKey, count = database.getHotpData(
            userEmail=recipientAddr.getEmailAddr(), 
        )

        hotp = getHotp(
            preSharedKey=preSharedKey,
            count=count,
            **{**context.hash, **context.hotp},
        )
        
        ## Adding the record to token database
        database.setSenderTokenUser(
            userEmail=recipientAddr.getEmailAddr(), 
            sender=sender, 
            count= count,
            token=hotp,
        )

        return {
            "token": hotp,
            "allowed_for": {
                "from": sender,
                "to": recipient,
                }
            }
    except ValueError:
        raise HTTPException(
            status_code=418,
            detail="Bad email address"
        )
    except PermissionError:
        raise HTTPException(
            status_code=406,
            detail="Policy not allowing this connection."
        ) 


## User-level API points requesting authentication
def auth(func):
    print("TODO: AUTH decorator")
    return func


@app.post("/{username}/")
@auth
async def home(username:str):
    """Only returns a welcoming message.
    Used for connection-testing sake.
    """
    return {"message": "Welcome " + username,
        "help":"See '/docs' for API documentation"
    }


@app.post("/{username}/getConfig")
@auth
async def home(username:str):
    """Returns server configurations useful for the client
    Including:
    - Cryptography configurations
    - Default configurations

    Args:
        username (str): user email address

    Returns:
        json: The json of configuration fields
    """
    return {"message": "Welcome " + username,
        "help":"See '/docs' for API documentation"
    }


@app.post("/{username}/generateHotpSeed")
@auth
async def generateHotpSeed(username:str, pubKey:str=Form()):
    """Regenerate seed (PSK) for Hotp generation from the user public key & returns the generated PSK seed, 
    the reinitialized counter and the server public key.
    ! The previous token generated with the elder seed become lapsed.

    Args:
        username (str): user email address.
        pubKey (str): user EC pubkey to generate ECDH PSK, given by POST form.

    Returns:
        json: formatted with {"user", "pubKey", "counter"}
    """
    
    logger.info(f'Request PSK for {username} with pubKey {pubKey}')

    logger.debug('Generating server private key.')
    serverPSK = PreSharedKey(
        **{**context.hash, **context.elliptic}
    )
    logger.debug('Generating PSK.')
    serverPSK.generate(
        user=username,
        recipientPubKey=pubKey,
    )
    counter = 0

    logger.debug('Saving PSK to database.')
    database.updatePsk(
        userEmail=username,
        psk=serverPSK.PSK,
        count=counter,
    )

    logger.debug('Returning public key and counter.')
    return {"user": username,
        "pubKey": serverPSK.exportPubKey(),
        "counter": counter,
    }


@app.get("/{username}/getCount")
@auth
async def getCount(username:str):
    
    (_, counter) = database.getHotpData(
        userEmail=username,
    )

    return {"username": username,
        "counter": counter,
    }


@app.get("/{username}/getAllTokens")
@auth
async def getAllTokens(username:str):
    
    tokens = database.getAllTokensUser(
        userEmail=username,
    )

    return {"username": username,
        "tokens": dict((token, sender) for token, sender in tokens),
    }

