package io.github.mcdrsingleplayer.mixin;

import io.github.mcdrsingleplayer.ConfluxNativeCache;
import java.nio.file.Path;
import net.fabricmc.loader.api.FabricLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

/** Conflux Map 0.1.6 also loads its native library from the integrated world. */
@Pseudo
@Mixin(targets = "cn.net.rms.confluxmap.nativepredict.NativeLib", remap = false)
public abstract class ConfluxNativeCacheMixin {
    @ModifyVariable(method = "init(Ljava/nio/file/Path;)Z", at = @At("HEAD"),
            argsOnly = true, ordinal = 0, remap = false, require = 0)
    private static Path mcdrCacheOutsideWorld(Path original) {
        return ConfluxNativeCache.directory(FabricLoader.getInstance().getGameDir());
    }
}
