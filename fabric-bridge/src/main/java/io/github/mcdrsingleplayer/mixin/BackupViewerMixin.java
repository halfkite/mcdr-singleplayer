package io.github.mcdrsingleplayer.mixin;

import io.github.mcdrsingleplayer.BackupViewerAccess;
import net.minecraft.client.gui.screens.worldselection.EditWorldScreen;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;

/**
 * 给存档编辑界面加一个只读访问器，供「查看存档」入口取当前存档名。
 *
 * 这里只 @Shadow 一个字段、不注入任何方法：widget 注册方法在 Screen 上是泛型的，
 * 早先用 @Shadow 去要它，擦除后在目标类里定位失败，直接让整个 EditWorldScreen
 * 转换失败、点「编辑」就报错。读取字段没有这个问题。
 *
 * 实现的接口必须放在 mixin 包外：mixin 包是保留包，
 * 普通类引用里面的类型会抛 IllegalClassLoadError 让游戏启动崩溃。
 */
@Mixin(EditWorldScreen.class)
public abstract class BackupViewerMixin implements BackupViewerAccess {
    @Shadow private net.minecraft.world.level.storage.LevelStorageSource.LevelStorageAccess levelAccess;

    @Override
    public String mcdr$worldId() {
        return levelAccess == null ? "" : String.valueOf(levelAccess.getLevelId());
    }
}
