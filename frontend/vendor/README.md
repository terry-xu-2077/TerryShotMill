# Shared UI build

`terry-react-ui-library-0.2.1-shotmill.1.tgz` is a locally built release of
Terry React UI Library, based on commit
`ba1474ac56ad9b15a2f09d51a1c910b811b83ec9`. It is not a parallel widget implementation.

The adjacent source patch adds a public `--tc-button-radius` token, `size="icon"`,
native button accessibility attributes, and a Showcase example. Existing defaults
remain compatible. ShotMill opts into capsule buttons through the public token.

Rebuild: check out the base commit in the upstream repository, apply
`terry-ui-capsule.patch`, install its dependencies, run `build:lib` and pack it.
The tarball is checked in so installation does not rely on the temporary source
checkout or mutate `node_modules`. No upstream commit has been pushed.

This is a versioned dependency snapshot, not a temporary runtime patch. Keep the
source patch with the archive until the shared library publishes these changes;
then replace both with a pinned upstream release. Local reconstruction checkouts
can be removed without affecting installation.

Archive SHA256:
`e6c9b3cde1a64e006e27c4f6e89bc18ad734fbd0a174d26b8dc6d842a432c1b9`
