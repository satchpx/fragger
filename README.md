# fragger
An attempt to induce fragmentation on the underlying storage/ filesystem

This does the following:
```
1. Run an fio-container, that overwrites a file. This terminates after an hour
2. snap the PVC every 30 minutes
```
