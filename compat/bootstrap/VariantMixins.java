package io.github.mcdrsingleplayer.bootstrap;

import java.util.List;
import java.util.Set;
import org.objectweb.asm.tree.ClassNode;
import org.spongepowered.asm.mixin.extensibility.IMixinConfigPlugin;
import org.spongepowered.asm.mixin.extensibility.IMixinInfo;

/** Only the active game adapter's mixins are loaded or inspected by Mixin. */
public final class VariantMixins implements IMixinConfigPlugin {
    @Override public void onLoad(String mixinPackage) {}
    @Override public String getRefMapperConfig() {
        String path = "mcdr-" + VersionSelector.current() + ".refmap.json";
        return VariantMixins.class.getResource("/" + path) == null ? null : path;
    }
    @Override public boolean shouldApplyMixin(String target, String mixin) { return true; }
    @Override public void acceptTargets(Set<String> mine, Set<String> others) {}
    @Override public List<String> getMixins() {
        String relative = VersionSelector.implementation().substring("io.github.mcdrsingleplayer.".length());
        return List.of(relative + ".RestoreWorldOpenMixin", relative + ".RestoreTitleScreenMixin");
    }
    @Override public void preApply(String target, ClassNode node, String mixin, IMixinInfo info) {}
    @Override public void postApply(String target, ClassNode node, String mixin, IMixinInfo info) {}
}
