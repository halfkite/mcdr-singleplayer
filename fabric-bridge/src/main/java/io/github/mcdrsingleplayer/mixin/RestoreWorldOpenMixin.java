package io.github.mcdrsingleplayer.mixin;

import io.github.mcdrsingleplayer.RestoreProgressMonitor;
import net.minecraft.client.gui.screens.worldselection.WorldOpenFlows;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(WorldOpenFlows.class)
abstract class RestoreWorldOpenMixin {
    @Inject(method = "openWorld", at = @At("HEAD"), cancellable = true)
    private void blockRestoringWorld(String world, Runnable onCancel, CallbackInfo callback) {
        if (RestoreProgressMonitor.blocks(world)) {
            RestoreProgressMonitor.showBlocked(world);
            callback.cancel();
        }
    }
}
