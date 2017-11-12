from setuptools import setup

import versioneer

commands = versioneer.get_cmdclass()

setup(name="magic-wormhole-transit-relay",
      version=versioneer.get_version(),
      description="Transit Relay server for Magic-Wormhole",
      author="Brian Warner",
      author_email="warner-magic-wormhole@lothar.com",
      license="MIT",
      url="https://github.com/warner/magic-wormhole-transit-relay",
      package_dir={"": "src"},
      packages=["wormhole_transit_relay",
                "wormhole_transit_relay.test",
                "twisted.plugins",
                ],
      package_data={"wormhole_transit_relay": ["db-schemas/*.sql"]},
      install_requires=[
          "twisted >= 17.5.0",
      ],
      extras_require={
          ':sys_platform=="win32"': ["pypiwin32"],
          "dev": ["mock", "tox", "pyflakes"],
      },
      test_suite="wormhole_transit_relay.test",
      cmdclass=commands,
      )
