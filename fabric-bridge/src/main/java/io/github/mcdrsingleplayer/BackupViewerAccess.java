package io.github.mcdrsingleplayer;

/**
 * 由 {@link io.github.mcdrsingleplayer.mixin.BackupViewerMixin} 混入 EditWorldScreen，
 * 用来读它私有的存档访问器。
 *
 * 这个接口必须放在 mixin 包**外面**：mixin 包是保留包（由 mcdrsingleplayer 的 mixin 配置
 * 声明），普通类直接引用里面的类型会在启动时抛 IllegalClassLoadError 并让游戏崩溃。
 * 原版界面没有公开这个字段，字段名运行时又被混淆，反射取不到，所以只能靠 mixin 桥接。
 */
public interface BackupViewerAccess {
    /** 存档文件夹名；读不到时返回空字符串。 */
    String mcdr$worldId();
}
