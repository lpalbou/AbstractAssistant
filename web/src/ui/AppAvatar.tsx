import { ActivityAvatar, type ActivityAvatarProps } from "../vendor/abstractavatar/activity_avatar.js";

/** A platform presenter for every design in AbstractAvatar's canonical catalog. */
export function AppAvatar(props: ActivityAvatarProps) {
  return <ActivityAvatar {...props} design={props.design ?? "watch-halo"} />;
}
