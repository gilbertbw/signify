# This is a derivative, modified, work from the verify-sigs project.
# Please refer to the LICENSE file in the distribution for more
# information. Original filename: auth_data_test.py
#
# Parts of this file are licensed as follows:
#
# Copyright 2012 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import hashlib
import io
import unittest
import pathlib

import binascii

import datetime

from signify.authenticode import CERTIFICATE_LOCATION, TRUSTED_CERTIFICATE_STORE
from signify.context import VerificationContext, FileSystemCertificateStore, CertificateStore
from signify.exceptions import VerificationError, AuthenticodeVerificationError, SignedPEParseError
from signify.fingerprinter import AuthenticodeFingerprinter
from signify.signed_pe import SignedPEFile

root_dir = pathlib.Path(__file__).parent
trusted_certificate_store = FileSystemCertificateStore(location=CERTIFICATE_LOCATION, trusted=True)


class AuthenticodeParserTestCase(unittest.TestCase):
    def test_software_update(self):
        with open(str(root_dir / "test_data" / "SoftwareUpdate.exe"), "rb") as f:
            fingerprinter = AuthenticodeFingerprinter(f)
            fingerprinter.add_authenticode_hashers(hashlib.sha1)
            hashes = fingerprinter.hash()

            # Sanity check that the authenticode hash is still correct
            self.assertEqual(binascii.hexlify(hashes['sha1']).decode('ascii'),
                             '978b90ace99c764841d2dd17d278fac4149962a3')

            pefile = SignedPEFile(f)

            # This should not raise any errors.
            signed_datas = list(pefile.signed_datas)
            # There may be multiple of these, if the windows binary was signed multiple
            # times, e.g. by different entities. Each of them adds a complete SignedData
            # blob to the binary. For our sample, there is only one blob.
            self.assertEqual(len(signed_datas), 1)
            signed_data = signed_datas[0]

            self.assertEqual(signed_data._rest_data, b'\0')

            signed_data.verify()

            # should work as well
            pefile.verify()

    def test_pciide(self):
        with open(str(root_dir / "test_data" / "pciide.sys"), "rb") as f:
            pefile = SignedPEFile(f)
            signed_datas = list(pefile.signed_datas)
            self.assertEqual(len(signed_datas), 1)
            signed_data = signed_datas[0]
            signed_data.verify()
            pefile.verify()

    def test_modified_pciide_fails(self):
        with open(str(root_dir / "test_data" / "pciide.sys"), "rb") as f:
            data = bytearray(f.read())
        data[1024] = 3
        bt = io.BytesIO(data)
        pefile = SignedPEFile(bt)
        signed_datas = list(pefile.signed_datas)
        self.assertEqual(len(signed_datas), 1)
        self.assertRaises(AuthenticodeVerificationError, signed_datas[0].verify)
        self.assertRaises(AuthenticodeVerificationError, pefile.verify)

    def test_simple(self):
        with open(str(root_dir / "test_data" / "simple"), "rb") as f:
            pefile = SignedPEFile(f)
            self.assertRaises(SignedPEParseError, list, pefile.signed_datas)
            self.assertRaises(SignedPEParseError, pefile.verify)

    def test_2A6E(self):
        with open(str(root_dir / "test_data" / "___2A6E.tmp"), "rb") as f:
            pefile = SignedPEFile(f)
            self.assertRaises(VerificationError, pefile.verify)

    def test_0d8c_valid(self):
        with open(str(root_dir / "test_data" / "0d8c2bcb575378f6a88d17b5f6ce70e794a264cdc8556c8e812f0b5f9c709198"), "rb") as f:
            pefile = SignedPEFile(f)
            pefile.verify()

    def test_19e8_expired(self):
        """this is an expired sample"""
        with open(str(root_dir / "test_data" / "19e818d0da361c4feedd456fca63d68d4b024fbbd3d9265f606076c7ee72e8f8.ViR"), "rb") as f:
            pefile = SignedPEFile(f)
            self.assertRaises(VerificationError, pefile.verify)

    def test_19e8_valid_within_period(self):
        """test whether the timestamp can be set on expired samples"""
        with open(str(root_dir / "test_data" / "19e818d0da361c4feedd456fca63d68d4b024fbbd3d9265f606076c7ee72e8f8.ViR"), "rb") as f:
            pefile = SignedPEFile(f)
            pefile.verify(verification_context_kwargs=
                          {'timestamp': datetime.datetime(2013, 1, 1, tzinfo=datetime.timezone.utc)})

    def test_sw_reporter(self):
        """Test for SHA256 hashes used in sig"""
        with open(str(root_dir / "test_data" / "software_reporter_tool.exe"), "rb") as f:
            pefile = SignedPEFile(f)
            signed_datas = list(pefile.signed_datas)
            self.assertEqual(len(signed_datas), 1)
            signed_data = signed_datas[0]
            signed_data.verify()
            pefile.verify()

    def test_7z1900_invalid_cve2020_0601(self):
        """This tests against CVE-2020-0601"""
        with open(str(root_dir / "test_data" / "7z1900-x64_signed.exe"), "rb") as f:
            pefile = SignedPEFile(f)
            self.assertRaises(VerificationError, pefile.verify)

    def test_3a7de393a36ca8911cd0842a9a25b058_valid_different_contenttype(self):
        """uses a different contenttype, 1.2.840.113549.1.9.16.1.4 instead of Data"""
        with open(str(root_dir / "test_data" / "3a7de393a36ca8911cd0842a9a25b058"), "rb") as f:
            pefile = SignedPEFile(f)
            pefile.verify()

    def test_solwarwinds_valid_countersignature_rfc3161(self):
        """Solarwinds includes a 1.3.6.1.4.1.311.3.3.1 type countersignature"""
        with open(str(root_dir / "test_data" / "SolarWinds.exe"), "rb") as f:
            pefile = SignedPEFile(f)
            pefile.verify()

    def test_whois_valid_countersignature_rfc3161(self):
        """whois includes a 1.3.6.1.4.1.311.3.3.1 type countersignature"""
        with open(str(root_dir / "test_data" / "whois.exe"), "rb") as f:
            pefile = SignedPEFile(f)
            pefile.verify()

    def test_jameslth_valid_when_revocation_not_checked(self):
        """this certificate is revoked"""
        with open(str(root_dir / "test_data" / "jameslth"), "rb") as f:
            pefile = SignedPEFile(f)
            pefile.verify()

    def test_jameslth_revoked(self):
        """this certificate is revoked"""
        with open(str(root_dir / "test_data" / "jameslth"), "rb") as f:
            pefile = SignedPEFile(f)
            with self.assertRaises(VerificationError):
                pefile.verify(verification_context_kwargs={'allow_fetching': True, 'revocation_mode': 'hard-fail'})

    def test_zonealarm_with_weird_countersignature(self):
        """this certificate is revoked"""
        with open(str(root_dir / "test_data" / "zonealarm.exe"), "rb") as f:
            pefile = SignedPEFile(f)
            pefile.verify()


class CertificateTestCase(unittest.TestCase):
    def test_all_trusted_certificates_are_trusted(self):
        context = VerificationContext(trusted_certificate_store)
        for certificate in trusted_certificate_store:
            # Trust depends on the timestamp
            context.timestamp = certificate.valid_to
            chain = certificate.verify(context)
            self.assertListEqual(chain, [certificate])

    def test_no_duplicates_in_default_store(self):
        self.assertEqual(len(TRUSTED_CERTIFICATE_STORE), len(set(TRUSTED_CERTIFICATE_STORE)))

    def test_trust_fails(self):
        # we get a certificate we currently trust
        for certificate in trusted_certificate_store:
            # we add it to an untrusted store
            store = CertificateStore(trusted=False)
            store.append(certificate)
            # and verify using this store
            context = VerificationContext(store, timestamp=certificate.valid_to)
            self.assertRaises(VerificationError, certificate.verify, context)

