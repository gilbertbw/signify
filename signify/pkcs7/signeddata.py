from pyasn1.codec.ber import decoder as ber_decoder
from pyasn1_modules import rfc2315, rfc5652

from signify import asn1, _print_type
from signify.asn1 import guarded_ber_decode
from signify.x509.certificates import Certificate
from signify.x509.context import CertificateStore
from signify.exceptions import ParseError
from signify.pkcs7.signerinfo import _get_digest_algorithm


class SignedData:
    """A generic SignedData object. The SignedData object is defined in RFC2315 and RFC5652 (amongst others) and
    defines data that is signed by one or more signers.

    It is based on the following ASN.1 object (as per RFC2315)::

        SignedData ::= SEQUENCE {
          version Version,
          digestAlgorithms DigestAlgorithmIdentifiers,
          contentInfo ContentInfo,
          certificates [0] IMPLICIT ExtendedCertificatesAndCertificates OPTIONAL,
          crls [1] IMPLICIT CertificateRevocationLists OPTIONAL,
          signerInfos SignerInfos
        }

    This class supports RFC2315 and RFC5652.

    .. attribute:: data

       The underlying ASN.1 data object

    .. attribute:: digest_algorithm

       The digest algorithm, i.e. the hash algorithm, that is used by the signers of the data.

    .. attribute:: content_type

       The class of the type of the content in the object.

    .. attribute:: content

       The actual content, as parsed by the :attr:`content_type` spec.

    .. attribute:: certificates
       :type: CertificateStore

       A list of all included certificates in the SignedData. These can be used to determine a valid validation path
       from the signer to a root certificate.

    .. attribute:: signer_infos
       :type: List[SignerInfo]

       A list of all included SignerInfo objects
    """

    _expected_content_type = None
    _signerinfo_class = None

    def __init__(self, data):
        """

        :param asn1.pkcs7.SignedData data: The ASN.1 structure of the SignedData object
        """

        if isinstance(self._signerinfo_class, str):
            self._signerinfo_class = globals()[self._signerinfo_class]

        self.data = data
        self._parse()

    @classmethod
    def from_envelope(cls, data, *args, **kwargs):
        """Loads a :class:`SignedData` object from raw data that contains ContentInfo.

        :param bytes data: The bytes to parse
        """
        # This one is not guarded, which is intentional
        content, rest = ber_decoder.decode(data, asn1Spec=rfc2315.ContentInfo())
        if asn1.oids.get(content['contentType']) is not rfc2315.SignedData:
            raise ParseError("ContentInfo does not contain SignedData")

        data = guarded_ber_decode(content['content'], asn1_spec=rfc2315.SignedData())

        signed_data = cls(data, *args, **kwargs)
        signed_data._rest_data = rest
        return signed_data

    def _parse(self):
        # digestAlgorithms
        if len(self.data['digestAlgorithms']) != 1:
            raise ParseError("SignedData.digestAlgorithms must contain exactly 1 algorithm, not %d" %
                             len(self.data['digestAlgorithms']))
        self.digest_algorithm = _get_digest_algorithm(self.data['digestAlgorithms'][0], "SignedData.digestAlgorithm")

        # contentType
        if isinstance(self.data, rfc2315.SignedData):
            self.content_type = asn1.oids.get(self.data['contentInfo']['contentType'])
            content = self.data['contentInfo']['content']
        elif isinstance(self.data, rfc5652.SignedData):
            self.content_type = asn1.oids.get(self.data['encapContentInfo']['eContentType'])
            content = self.data['encapContentInfo']['eContent']
        else:
            raise ParseError("Unknown SignedData data type {}".format(_print_type(self.data)))

        if self.content_type is not self._expected_content_type:
            raise ParseError("SignedData.contentInfo does not contain %s" % _print_type(self._expected_content_type))

        # Content
        self.content = guarded_ber_decode(content, asn1_spec=self._expected_content_type())

        # Certificates
        self.certificates = CertificateStore(
            [Certificate(cert) for cert in self.data['certificates'] if Certificate.is_certificate(cert)]
        )

        # SignerInfo
        if self._signerinfo_class is not None:
            self.signer_infos = [self._signerinfo_class(si, parent=self) for si in self.data['signerInfos']]