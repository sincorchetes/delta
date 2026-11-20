"""D-Bus interface definition exposed by the Delta daemon."""

INTERFACE_NAME = "io.github.sincorchetes.Delta.Service1"
OBJECT_PATH = "/io/github/sincorchetes/Delta/Service1"

INTERFACE_XML = """
<node>
  <interface name="io.github.sincorchetes.Delta.Service1">
    <method name="CreateBackup">
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <method name="CreateRepository">
      <arg name="location" type="s" direction="in"/>
      <arg name="passphrase" type="s" direction="in"/>
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <method name="UnlockRepository">
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <method name="UseRepository">
      <arg name="location" type="s" direction="in"/>
      <arg name="passphrase" type="s" direction="in"/>
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <method name="ListSnapshots">
      <arg name="snapshots" type="aa{sv}" direction="out"/>
    </method>
    <method name="ListVersions">
      <arg name="path" type="s" direction="in"/>
      <arg name="versions" type="aa{sv}" direction="out"/>
    </method>
    <method name="ListFolder">
      <arg name="snapshot_id" type="s" direction="in"/>
      <arg name="path" type="s" direction="in"/>
      <arg name="entries" type="aa{sv}" direction="out"/>
    </method>
    <method name="SearchFolder">
      <arg name="snapshot_id" type="s" direction="in"/>
      <arg name="path" type="s" direction="in"/>
      <arg name="query" type="s" direction="in"/>
      <arg name="entries" type="aa{sv}" direction="out"/>
    </method>
    <method name="ListDeleted">
      <arg name="snapshot_id" type="s" direction="in"/>
      <arg name="folder" type="s" direction="in"/>
      <arg name="entries" type="aa{sv}" direction="out"/>
    </method>
    <method name="ListChanged">
      <arg name="snapshot_id" type="s" direction="in"/>
      <arg name="folder" type="s" direction="in"/>
      <arg name="entries" type="aa{sv}" direction="out"/>
    </method>
    <method name="RestoreDeleted">
      <arg name="snapshot_id" type="s" direction="in"/>
      <arg name="folder" type="s" direction="in"/>
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <method name="Restore">
      <arg name="snapshot_id" type="s" direction="in"/>
      <arg name="source_path" type="s" direction="in"/>
      <arg name="target_path" type="s" direction="in"/>
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <method name="RestoreAsCopy">
      <arg name="snapshot_id" type="s" direction="in"/>
      <arg name="path" type="s" direction="in"/>
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <method name="RestoreReplace">
      <arg name="snapshot_id" type="s" direction="in"/>
      <arg name="path" type="s" direction="in"/>
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <method name="PreviewVersion">
      <arg name="snapshot_id" type="s" direction="in"/>
      <arg name="path" type="s" direction="in"/>
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <method name="ClearPreviews"/>
    <method name="MountSnapshot">
      <arg name="snapshot_id" type="s" direction="in"/>
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <method name="UnmountSnapshot">
      <arg name="job_id" type="s" direction="out"/>
    </method>
    <signal name="SnapshotClosed">
      <arg name="reason" type="s"/>
    </signal>
    <signal name="Progress">
      <arg type="s"/>
      <arg type="d"/>
      <arg type="s"/>
    </signal>
    <signal name="BackupFinished">
      <arg type="s"/>
      <arg type="b"/>
      <arg type="s"/>
    </signal>
    <property name="Status" type="s" access="read"/>
    <property name="LastBackup" type="t" access="read"/>
    <property name="NextBackup" type="t" access="read"/>
    <property name="LastError" type="s" access="read"/>
    <property name="UnavailableReason" type="s" access="read"/>
    <property name="CanMount" type="b" access="read"/>
  </interface>
</node>
"""
