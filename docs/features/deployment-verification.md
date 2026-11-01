# Verify which version is deployed

CI/CD exists in `.github/workflows/docker-build.yml`. A PR runs lint, Django,
HTTP and browser checks. A push to `main` additionally publishes the multi-arch
image, promotes the `main` tag, calls the production Portainer webhook and polls
`/api/v1/version/` to verify that the server runs the expected commit (or a later
main commit). A green PR alone does not publish a production version.

Production uses the GitHub `production` environment's `PORTAINER_WEBHOOK_URL`
secret and `SITE_URL` variable. Do not print or commit the webhook value.

```sh
gh run list --workflow docker-build.yml --branch main --limit 5
gh pr view <number> --json state,baseRefName,mergeCommit
curl -fsS https://library.fazelukario.me/api/v1/version/
git fetch origin
git merge-base --is-ancestor <feature-commit> origin/main
```

Inspect the run's `deploy` job for both `Redeploy triggered` and `Redeploy
confirmed`. If the feature commit is not an ancestor of main, deploying main
cannot make that feature appear.

## Incident on 2026-11-01

Run 41319035905 successfully tested and deployed `81c4bf0` to production.
That main commit did not contain ratings. KAN-59, KAN-60 and KAN-61 were merged
into their preceding feature branches **after** the parent KAN-51 PR had already
been merged into main. GitHub's “Merged” state on those child PRs therefore did
not imply that their code reached main. This repair PR includes the stranded
rating commits and is based directly on main, including the administrator role.
No manual production deployment is part of the repair.

For future stacked PRs, merge children into their open parent before merging the
parent to main, or retarget the child to main after its parent merges and update
it against main. Check commit ancestry before treating a feature as deployed.
