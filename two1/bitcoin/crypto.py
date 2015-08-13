import base58
import base64
import hashlib
import math
import random

from two1.bitcoin.utils import bytes_to_str, address_to_key_hash
from two1.crypto.ecdsa import ECPointAffine, ECPointJacobian, EllipticCurve, secp256k1

bitcoin_curve = secp256k1()


def get_bytes(s):
    if isinstance(s, bytes):
        b = s
    elif isinstance(s, str):
        b = bytes.fromhex(s)
    else:
        raise TypeError("s must be either 'bytes' or 'str'!")

    return b
    
class PrivateKey(object):
    """ Encapsulation of a Bitcoin ECDSA private key.

        This class provides capability to generate private keys,
        obtain the corresponding public key, sign messages and
        serialize/deserialize into a variety of formats.

    Args:
        k (int): The private key.

    Returns:
        PrivateKey: The object representing the private key.
    """
    TESTNET_VERSION = 0xEF
    MAINNET_VERSION = 0x80

    @staticmethod
    def from_int(i):
        """ Initializes a private key from an integer.

        Args:
            i (int): Integer that is the private key.

        Returns:
            PrivateKey: The object representing the private key.
        """
        return PrivateKey(i)

    @staticmethod
    def from_b58check(private_key):
        """ Decodes a Base58Check encoded private-key.

        Args:
            private_key (str): A Base58Check encoded private key.

        Returns:
            PrivateKey: A PrivateKey object
        """
        b58dec = base58.b58decode_check(private_key)
        version = b58dec[0]
        assert version in [PrivateKey.TESTNET_VERSION, PrivateKey.MAINNET_VERSION]
        
        return PrivateKey(int.from_bytes(b58dec[1:], 'big'))

    @staticmethod
    def from_random():
        """ Initializes a private key from a random integer.

        Returns:
            PrivateKey: The object representing the private key.
        """
        return PrivateKey(random.SystemRandom().randrange(1, bitcoin_curve.n - 1))

    def __init__(self, k):
        self.key = k        
        self._public_key = PublicKey.from_point(bitcoin_curve.public_key(self.key))

    @property
    def public_key(self):
        """ Returns the public key associated with this private key.
        
        Returns:
            PublicKey: The PublicKey object that corresponds to this private key.
        """
        return self._public_key

    def raw_sign(self, message, do_hash=True):
        """ Signs message using this private key.

        Args:
            message (bytes): The message to be signed. If a string is provided
               it is assumed the encoding is 'ascii' and converted to bytes. If this is
               not the case, it is up to the caller to convert the string to bytes
               appropriately and pass in the bytes.
            do_hash (bool): True if the message should be hashed prior
               to signing, False if not. This should always be left as
               True except in special situations which require doing
               the hash outside (e.g. handling Bitcoin bugs).

        Returns:
            ECPointAffine: a raw point (r = pt.x, s = pt.y) which is the signature.
        """
        if isinstance(message, str):
            msg = bytes(message, 'ascii')
        elif isinstance(message, bytes):
            msg = message
        else:
            raise TypeError("message must be either str or bytes!")

        return bitcoin_curve.sign(msg, self.key, do_hash)

    def sign(self, message, do_hash=True):
        """ Signs message using this private key.

        Note:
            This differs from `raw_sign()` since it returns a Signature object.

        Args:
            message (bytes or str): The message to be signed. If a string is provided
               it is assumed the encoding is 'ascii' and converted to bytes. If this is
               not the case, it is up to the caller to convert the string to bytes
               appropriately and pass in the bytes.
            do_hash (bool): True if the message should be hashed prior
               to signing, False if not. This should always be left as
               True except in special situations which require doing
               the hash outside (e.g. handling Bitcoin bugs).

        Returns:
            Signature: The signature corresponding to message.
        """
        # Some BTC things want to have the recovery id to extract the public
        # key, so we should figure that out.
        sig_pt, rec_id = self.raw_sign(message, do_hash)

        return Signature(sig_pt.x, sig_pt.y, rec_id)

    def sign_bitcoin(self, message):
        """ Signs a message using this private key such that it
            is compatible with bitcoind, bx, and other Bitcoin
            clients/nodes/utilities.

        Note:
            b"\x18Bitcoin Signed Message:\n" + len(message) is prepended
            to the message before signing.

        Args:
            message (bytes or str): Message to be signed.

        Returns:
            bytes: A Base64-encoded byte string of the signed message.
               The first byte of the encoded message contains information
               about how to recover the public key. In bitcoind parlance,
               this is the magic number containing the recovery ID and
               whether or not the key was compressed or not. (This function
               always processes full, uncompressed public-keys, so the magic
               number will always be either 27 or 28).
        """
        if isinstance(message, str):
            msg_in = bytes(message, 'ascii')
        elif isinstance(message, bytes):
            msg_in = message
        else:
            raise TypeError("message must be either str or bytes!")

        msg = b"\x18Bitcoin Signed Message:\n" + bytes([len(msg_in)]) + msg_in
        msg_hash = hashlib.sha256(msg).digest()

        sig = self.sign(msg_hash)
        magic = 27 + sig.recovery_id
    
        return base64.b64encode(bytes([magic]) + bytes(sig))

    def to_b58check(self, testnet=False):
        """ Generates a Base58Check encoding of this private key.

        Returns:
            str: A Base58Check encoded string representing the key.
        """
        version = self.TESTNET_VERSION if testnet else self.MAINNET_VERSION
        return base58.b58encode_check(bytes([version]) + bytes(self))

    def to_hex(self):
        """ Generates a hex encoding of the serialized key.

        Returns:
           str: A hex encoded string representing the key.
        """
        return bytes_to_str(bytes(self))

    def __bytes__(self):
        return self.key.to_bytes(32, 'big')

    def __int__(self):
        return self.key

    
class PublicKey(object):
    """ Encapsulation of a Bitcoin ECDSA public key.

        This class provides a high-level API to using an ECDSA public
        key, specifically for Bitcoin (secp256k1) purposes.

    Args:
        x (int): The x component of the public key point.
        y (int): The y component of the public key point.

    Returns:
        PublicKey: The object representing the public key.
    """
    
    TESTNET_VERSION = 0x6F
    MAINNET_VERSION = 0x00

    @staticmethod
    def from_point(p):
        """ Generates a public key object from any object
            containing x, y coordinates.

        Args:
            p (Point): An object containing a two-dimensional, affine
               representation of a point on the secp256k1 curve.

        Returns:
            PublicKey: A PublicKey object.
        """
        return PublicKey(p.x, p.y)
    
    @staticmethod
    def from_int(i):
        """ Generates a public key object from an integer.

        Note:
            This assumes that the upper 32 bytes of the integer
            are the x component of the public key point and the
            lower 32 bytes are the y component.

        Args:
            i (Bignum): A 512-bit integer representing the public
               key point on the secp256k1 curve.

        Returns:
            PublicKey: A PublicKey object.
        """
        point = ECPointAffine.from_int(bitcoin_curve, i)
        return PublicKey.from_point(point)

    @staticmethod
    def from_base64(b64str, testnet=False):
        """ Generates a public key object from a Base64 encoded string.

        Args:
            b64str (str): A Base64-encoded string.
            testnet (bool) (Optional): If True, changes the version that
               is prepended to the key.

        Returns:
            PublicKey: A PublicKey object.
        """
        return PublicKey.from_bytes(base64.b64decode(b64str))
    
    @staticmethod
    def from_bytes(key_bytes):
        """ Generates a public key object from a byte (or hex) string.

            The byte stream must be of the SEC variety
            (http://www.secg.org/): beginning with a single byte telling
            what key representation follows. A full, uncompressed key
            is represented by: 0x04 followed by 64 bytes containing
            the x and y components of the point. For compressed keys
            with an even y component, 0x02 is followed by 32 bytes
            containing the x component. For compressed keys with an
            odd y component, 0x03 is followed by 32 bytes containing
            the x component.
            
        Args:
            key_bytes (bytes or str): A byte stream that conforms to the above.

        Returns:
            PublicKey: A PublicKey object.
        """
        b = get_bytes(key_bytes)
        key_bytes_len = len(b)

        key_type = b[0]
        if key_type == 0x04:
            # Uncompressed
            if key_bytes_len != 65:
                raise ValueError("key_bytes must be exactly 65 bytes long when uncompressed.")

            x = int.from_bytes(b[1:33], 'big')
            y = int.from_bytes(b[33:65], 'big')
        elif key_type == 0x02 or key_type == 0x03:
            if key_bytes_len != 33:
                raise ValueError("key_bytes must be exactly 33 bytes long when compressed.")

            x = int.from_bytes(b[1:33], 'big')
            ys = bitcoin_curve.y_from_x(x)

            # Pick the one that corresponds to key_type
            last_bit = key_type - 0x2
            for y in ys:
                if y & 0x1 == last_bit:
                    break
        else:
            return None

        return PublicKey(x, y)

    @staticmethod
    def from_private_key(private_key):
        """ Generates a public key object from a PrivateKey object.

        Args:
            private_key (PrivateKey): The private key object from
               which to derive this object.

        Returns:
            PublicKey: A PublicKey object.
        """
        return private_key.public_key

    @staticmethod
    def from_signature(message, signature):
        """ Attempts to create PublicKey object by deriving it
            from the message and signature.

        Args:
            message (bytes): The message to be verified.
            signature (Signature): The signature for message.
               The recovery_id must not be None!

        Returns:
            PublicKey: A PublicKey object derived from the
               signature, it it exists. None otherwise.
        """
        if signature.recovery_id is None:
            raise ValueError("The signature must have a recovery_id.")
        
        msg = get_bytes(message)
        pub_keys = bitcoin_curve.recover_public_key(msg, signature, signature.recovery_id)
        
        for k, recid in pub_keys:
            if signature.recovery_id is not None and recid == signature.recovery_id:
                return PublicKey(k.x, k.y)

        return None

    @staticmethod
    def verify_bitcoin(message, signature):
        """ Verifies a message signed using PrivateKey.sign_bitcoin()
            or any of the bitcoin utils (e.g. bitcoin-cli, bx, etc.)

        Args:
            signature (bytes or str): A Base64 encoded signature

        Returns:
            bool: True if the signature verified properly, False otherwise.
        """
        sig_bytes = get_bytes(signature)
        magic_sig = base64.b64decode(signature)

        magic = magic_sig[0]
        sig = Signature.from_bytes(magic_sig[1:])
        sig.recovery_id = magic - 27

        # Build the message that was signed
        msg = b"\x18Bitcoin Signed Message:\n" + bytes([len(message)]) + message
        msg_hash = hashlib.sha256(msg).digest()

        derived_public_key = PublicKey.from_signature(msg_hash, sig)
        if derived_public_key is None:
            raise ValueError("Could not recover public key from the provided signature.")

        return derived_public_key.verify(msg_hash, sig)
    
    def __init__(self, x, y):
        p = ECPointAffine(bitcoin_curve, x, y)
        if not bitcoin_curve.is_on_curve(p):
            raise ValueError("The provided (x, y) are not on the secp256k1 curve.")

        self.point = p

        # RIPEMD-160 of SHA-256
        r = hashlib.new('ripemd160')
        r.update(hashlib.sha256(bytes(self)).digest())
        self.ripe = r.digest()

        r = hashlib.new('ripemd160')
        r.update(hashlib.sha256(self.compressed_bytes).digest())
        self.ripe_compressed = r.digest()

    def hash160(self, compressed=True):
        """ Return the RIPEMD-160 hash of the SHA-256 hash of the
            uncompressed public key.

        Args:
            compressed (bool): Whether or not the compressed key should
               be used.
        Returns
            bytes: RIPEMD-160 byte string.
        """
        return self.ripe_compressed if compressed else self.ripe
        
    def address(self, compressed=True, testnet=False):
        """ Address property that returns the Base58Check
            encoded version of the HASH160.

        Args:
            compressed (bool): Whether or not the compressed key should
               be used.
            testnet (bool): Whether or not the key is intended for testnet
               usage. False indicates mainnet usage.

        Returns:
            bytes: Base58Check encoded string
        """
        # Put the version byte in front, 0x00 for Mainnet, 0x6F for testnet
        version = bytes([self.TESTNET_VERSION]) if testnet else bytes([self.MAINNET_VERSION])
        return base58.b58encode_check(version + self.hash160(compressed))
    
    def verify(self, message, signature, do_hash=True):
        """ Verifies that message was appropriately signed.

        Args:
            message (bytes): The message to be verified.
            signature (Signature): A signature object.
            do_hash (bool): True if the message should be hashed prior
               to signing, False if not. This should always be left as
               True except in special situations which require doing
               the hash outside (e.g. handling Bitcoin bugs).

        Returns:
            verified (bool): True if the signature is verified, False otherwise.
        """
        msg = get_bytes(message)
        return bitcoin_curve.verify(msg, signature, self.point, do_hash)
    
    def to_hex(self):
        """ Hex representation of the serialized byte stream.

        Returns:
            h (str): A hex-encoded string.
        """
        return bytes_to_str(bytes(self))

    def to_base64(self):
        """ Hex representation of the serialized byte stream.

        Returns:
            b (str): A Base64-encoded string.
        """
        return base64.b64encode(bytes(self))

    def __int__(self):
        mask = 2 ** 256 - 1
        return ((self.point.x & mask) << bitcoin_curve.nlen) | (self.point.y & mask)

    def __bytes__(self):
        return bytes(self.point)

    @property
    def compressed_bytes(self):
        """ Byte string corresponding to a compressed representation
            of this public key.

        Returns:
            b (bytes): A 33-byte long byte string.
        """
        return self.point.compressed_bytes


class Signature(object):
    """ Encapsulation of a ECDSA signature for Bitcoin purposes.

    Args:
        r (Bignum): r component of the signature.
        s (Bignum): s component of the signature.
        recovery_id (int) (Optional): Must be between 0 and 3 specifying
           which of the public keys generated by the algorithm specified
           in http://www.secg.org/sec1-v2.pdf Section 4.1.6 (Public Key
           Recovery Operation) is the correct one for this signature.

    Returns:
        sig (Signature): A Signature object.
    """
    
    @staticmethod
    def from_der(der):
        """ Decodes a Signature that was DER-encoded.

        Args:
            der (bytes or str): The DER encoding to be decoded.

        Returns:
            Signature: The deserialized signature.
        """
        d = get_bytes(der)
        # d must conform to (from btcd):
        # 0x30 <length> 0x02 <length r> r 0x02 <length s> s
        
        if len(d) < 8:
            raise ValueError("DER signature string is too short.")
        if d[0] != 0x30:
            raise ValueError("DER signature does not start with 0x30.")
        if d[1] != len(d[2:]):
            raise ValueError("DER signature length incorrect.")

        total_length = d[1]
        
        if d[2] != 0x02:
            raise ValueError("DER signature no 1st int marker.")
        if d[3] <= 0 or d[3] > (total_length - 7):
            raise ValueError("DER signature incorrect r length.")

        # Grab R, check for errors
        rlen = d[3]
        s_magic_index = 4 + rlen
        rb = d[4:s_magic_index]

        if rb[0] & 0x80 != 0:
            raise ValueError("DER signature R is negative.")
        if len(rb) > 1 and rb[0] == 0 and rb[1] & 0x80 != 0x80:
            raise ValueError("DER signature R is excessively padded.")

        r = int.from_bytes(rb, 'big')

        # Grab S, check for errors
        if d[s_magic_index] != 0x02:
            raise ValueError("DER signature no 2nd int marker.")
        slen_index = s_magic_index + 1
        slen = d[slen_index]
        if slen <= 0 or slen > len(d) - (slen_index + 1):
            raise ValueError("DER signature incorrect s length.")

        sb = d[slen_index + 1:]

        if sb[0] & 0x80 != 0:
            raise ValueError("DER signature S is negative.")
        if len(sb) > 1 and sb[0] == 0 and sb[1] & 0x80 != 0x80:
            raise ValueError("DER signature S is excessively padded.")

        s = int.from_bytes(sb, 'big')

        if r < 1 or r >= bitcoin_curve.n:
            raise ValueError("DER signature R is not between 1 and N - 1.")
        if s < 1 or s >= bitcoin_curve.n:
            raise ValueError("DER signature S is not between 1 and N - 1.")
        
        return Signature(r, s)

    @staticmethod
    def from_base64(b64str):
        """ Generates a signature object from a Base64 encoded string.

        Args:
            b64str (str): A Base64-encoded string.

        Returns:
            Signature: A Signature object.
        """
        return Signature.from_bytes(base64.b64decode(b64str))
    
    @staticmethod
    def from_bytes(b):
        """ Extracts the r and s components from a byte string.
        
        Args:
            b (bytes): A 64-byte long string. The first 32 bytes are
               extracted as the r component and the second 32 bytes
               are extracted as the s component.

        Returns:
            Signature: A Signature object.
        """
        r = int.from_bytes(b[0:32], 'big')
        s = int.from_bytes(b[32:64], 'big')
        return Signature(r, s)
    
    def __init__(self, r, s, recovery_id=None):
        self.r = r
        self.s = s
        self.recovery_id = recovery_id

    @property
    def x(self):
        """ Convenience property for any method that requires
            this object to provide a Point interface.
        """
        return self.r

    @property
    def y(self):
        """ Convenience property for any method that requires
            this object to provide a Point interface.
        """
        return self.s

    def _canonicalize(self):
        rv = []
        for x in [self.r, self.s]:
            # Compute minimum bytes to represent integer
            bl = math.ceil(x.bit_length() / 8)
            # Make sure it's at least one byte in length
            if bl == 0:
                bl += 1
            x_bytes = x.to_bytes(bl, 'big')

            # make sure there's no way it could be interpreted
            # as a negative integer
            if x_bytes[0] & 0x80:
                x_bytes = bytes([0]) + x_bytes

            rv.append(x_bytes)

        return rv
    
    def to_der(self):
        """ Encodes this signature using DER

        Returns:
            bytes: The DER encoding of (self.r, self.s).
        """
        # Output should be:
        # 0x30 <length> 0x02 <length r> r 0x02 <length s> s
        r, s = self._canonicalize()

        total_length = 6 + len(r) + len(s)
        der = bytes([0x30, total_length - 2, 0x02, len(r)]) + r + bytes([0x02, len(s)]) + s
        return der

    def to_hex(self):
        """ Hex representation of the serialized byte stream.

        Returns:
            str: A hex-encoded string.
        """
        return bytes_to_str(bytes(self))
    
    def to_base64(self):
        """ Hex representation of the serialized byte stream.

        Returns:
            str: A Base64-encoded string.
        """
        return base64.b64encode(bytes(self))

    def __bytes__(self):
        nbytes = math.ceil(bitcoin_curve.nlen / 8)
        return self.r.to_bytes(nbytes, 'big') + self.s.to_bytes(nbytes, 'big')